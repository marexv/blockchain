import hashlib
import json
from time import time
from urllib.parse import urlparse
from uuid import uuid4

import requests
from flask import Flask, jsonify, request


class Blokchain(object):

    def __init__(self):
        self.chain = []
        self.current_transactions = []
        self.nodes = set()

        # Create the genesis block.
        self.new_block(previous_hash=1, proof=100)

    def new_block(self, proof, previous_hash=None):
        """
        Create a new Block in the Blockchain.

        :param proof: <int> The proof given by the proof of work algorithm
        :param previous_hash (Optional): <str> Hash of previous Block
        :return: <dict> New Block
        """
        block = {
            "index": len(self.chain) + 1,
            "timestamp": time(),
            "transactions": self.current_transactions,
            "proof": proof,
            "previous_hash": previous_hash or self.hash(self.chain[-1]),
        }

        # Reset current list of transactions.
        self.current_transactions = []

        self.chain.append(block)

        return block

    def new_transaction(self, sender, recipient, amount):
        """
        Create a new transaction to go into next mined Block.
        :param sender: <str> Address of the Sender.
        :param recipinet: <str> Address of the recipient.
        :param amount: <int> Amount.
        :return: <int> The index of the Block that will hold this transaction.
        """
        self.current_transactions.append({
            "sender": sender,
            "recipient": recipient,
            "amount": amount,
        })

        return self.last_block['index'] + 1

    @property
    def last_block(self):
        """Return the last Block in the chain."""
        return self.chain[-1]

    @staticmethod
    def hash(block):
        """
        Create a SHA-256 hash of a Block

        :param block: <dict> Block
        :return: <str>
        """
        block_string = json.dumps(block, sort_keys=True).encode()

        return hashlib.sha256(block_string).hexdigest()

    def proof_of_work(self, last_proof):
        """
        Simple proof of work Algorithm:
        - Find a number p' such that hash(pp') contains leading 4 zeroes, where 
        p is the previous p'
        - p is the previous proof, and p' is the new proof

        :param last_proof: <int>
        :return: <int>
        """
        proof = 0
        while self.valid_proof(last_proof, proof) is False:
            proof += 1

        return proof


    @staticmethod
    def valid_proof(last_proof, proof):
        """
        Validates the Proof: Does hash(last_proof, proof) contain 4 leading 0?

        :return last_proof: <int> Previous proof
        :return proof: <int> Current Proof
        :return: <bool> True if correct, False if not.
        """
        guess = f"{last_proof}{proof}".encode()
        guess_hash = hashlib.sha256(guess).hexdigest()
        return guess_hash[:4] == "0000"

    def register_node(self, address):
        """
        Add a new node to the list of nodes

        :param address: <str> Address of node. Eg. 'http://192,168.0.5:5000'
        :return: None
        """
        parsed_url = urlparse(address)
        self.nodes.add(parsed_url.netloc)

    def valid_chain(self, chain):
        """
        Determine if a given blokchain is valid

        :param chain: <list> A blokchain
        :return: <bool> True if valid, False if not
        """
        last_block = chain[0]
        current_index = 1

        while current_index < len(chain):
            block = chain[current_index]
            print(f"{last_block}")
            print(f"{block}")
            print("\n----------\n")
            # Check that the hash of the block is correct
            if block["previous_hash"] != self.hash(last_block):
                return False

            if not self.valid_proof(last_block["proof"], block["proof"]):
                return False

            last_block = block
            current_index += 1

        return True

    def resolve_conflict(self):
        """
        This is our Consenus Algorithm, it resolves conflict
        by replacing our chain with the longest one in the network.

        :return: <bool> True if our chain was replaced, False if not
        """
        neighbours = self.nodes
        new_chain = None

        # We're only looking for chains longer than ours
        max_lenght = len(self.chain)
        print(f"Max length: {max_lenght}")

        # Grab and verify the chains from all the nodes in our network
        for node in neighbours:
            response = requests.get(f"http://{node}/chain")

            if response.status_code == 200:
                length = response.json()["length"]
                chain = response.json()["chain"]

                # Checko if the length is longer and the chain is valid
                if length > max_lenght and self.valid_chain(chain):
                    max_lenght = length
                    new_chain = chain
       
        # Replace our chain if we discover an new, valid chain longer than ours
        if new_chain:
            self.chain = new_chain
            return True

        return False

# Server part

# Instantiate our Node
app = Flask(__name__)

# Generate a globally unique address for this node
node_identifier = str(uuid4()).replace("-", "")

# Instantianate the Blokchain
blokchain = Blokchain()

@app.route("/mine", methods=["GET"])
def mine():
    # We run the proof of work algorithm to get the next proof.
    last_block = blokchain.last_block
    last_proof = last_block["proof"]
    proof = blokchain.proof_of_work(last_proof)

    # We must receive a reward for finding the proof.
    # The sender is "0" to signify that this node has mined a new coin.
    blokchain.new_transaction(
        sender="0",
        recipient=node_identifier,
        amount=1,
    )

    # Forge the new BLock by adding it to the chain
    previous_hash = blokchain.hash(last_block)
    block = blokchain.new_block(proof, previous_hash)

    response = {
        "message": "New Block Forged",
        "index": block["index"],
        "transactions": block["transactions"],
        "proof": block["proof"],
        "previous_hash": block["previous_hash"],
    }

    return jsonify(response), 200


@app.route("/transactions/new", methods=["POST"])
def new_transaction():
    values = request.get_json()

    # Check thath required fields are in the POST'ed data
    required = ["sender", "recipient", "amount"]
    if not all(k in values for k in required):
        return "Missign values", 400

    # Create a new Transaction
    index = blokchain.new_transaction(values["sender"],
                                      values["recipient"],
                                      values["amount"])

    response = {"message": f"Transaction will be added to Block {index}"}
    return jsonify(response), 201


@app.route("/chain", methods=["GET"])
def full_chain():
    response = {
        "chain": blokchain.chain,
        "length": len(blokchain.chain),
    }
    return jsonify(response), 200

@app.route("/nodes/register", methods=["POST"])
def register_nodes():
    values = request.get_json()

    nodes = values.get("nodes")
    if nodes is None:
        return "Error: Please supply a valid list of nodes", 400

    for node in nodes:
        blokchain.register_node(node)

    response = {
        "message": "New nodes have been added",
        "total_nodes": list(blokchain.nodes),
    }

    return jsonify(response), 201

@app.route("/nodes/resolve", methods=["GET"])
def consensus():
    replaced = blokchain.resolve_conflict()

    if replaced:
        response = {
            "message": "Our chain was replaced",
            "new_chain": blokchain.chain
        }
    else:
        response = {
            "message": "Our chain is authoritative",
            "chain": blokchain.chain
        }

    return jsonify(response), 200


if __name__ == "__main__":
    from argparse import ArgumentParser

    parser = ArgumentParser()
    parser.add_argument('-p', '--port', default=5000, type=int, help='port to listen on')
    args = parser.parse_args()
    port = args.port

    app.run(host='0.0.0.0', port=port)
