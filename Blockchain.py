import hashlib
import json
from time import time
from uuid import uuid4
from fastapi import FastAPI, Request, HTTPException, Form
from pydantic import BaseModel
from urllib.parse import urlparse
import requests
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

class Blockchain:
    def __init__(self):
        self.chain = []
        self.current_transactions = []
        self.new_block(previous_hash='1', proof=100)
        self.nodes = set()

    def new_block(self, proof, previous_hash=None):
        block = {
            'index': len(self.chain) + 1,
            'timestamp': time(),
            'transactions': self.current_transactions,
            'proof': proof,
            'previous_hash': previous_hash or self.hash(self.chain[-1]),
        }
        self.current_transactions = []
        self.chain.append(block)
        return block

    def new_transaction(self, sender, recipient, amount):
        self.current_transactions.append({
            'sender': sender,
            'recipient': recipient,
            'amount': amount,
        })
        return self.last_block['index'] + 1

    def register_node(self, address):
        parsed_url = urlparse(address)
        self.nodes.add(parsed_url.netloc)

    def valid_chain(self, chain):
        last_block = chain[0]
        current_index = 1

        while current_index < len(chain):
            block = chain[current_index]
            if block['previous_hash'] != self.hash(last_block):
                return False
            if not self.valid_proof(last_block['proof'], block['proof']):
                return False
            last_block = block
            current_index += 1
        return True

    def resolve_conflicts(self):
        neighbours = self.nodes
        new_chain = None
        max_length = len(self.chain)

        for node in neighbours:
            response = requests.get(f'http://{node}/chain')
            if response.status_code == 200:
                length = response.json()['length']
                chain = response.json()['chain']
                if length > max_length and self.valid_chain(chain):
                    max_length = length
                    new_chain = chain

        if new_chain:
            self.chain = new_chain
            return True
        return False

    @staticmethod
    def hash(block):
        block_string = json.dumps(block, sort_keys=True).encode()
        return hashlib.sha256(block_string).hexdigest()

    @property
    def last_block(self):
        return self.chain[-1]

    def proof_of_work(self, last_proof):
        proof = 0
        while not self.valid_proof(last_proof, proof):
            proof += 1
        return proof

    @staticmethod
    def valid_proof(last_proof, proof):
        guess = f'{last_proof}{proof}'.encode()
        guess_hash = hashlib.sha256(guess).hexdigest()
        return guess_hash[:4] == "0000"

blockchain = Blockchain()
node_identifier = str(uuid4()).replace('-', '')

class Transaction(BaseModel):
    sender: str
    recipient: str
    amount: int

@app.get("/", response_class=HTMLResponse)
async def read_index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get('/mine', response_class=HTMLResponse)
async def mine(request: Request):
    last_block = blockchain.last_block
    last_proof = last_block['proof']
    proof = blockchain.proof_of_work(last_proof)
    blockchain.new_transaction(sender="0", recipient=node_identifier, amount=1)
    previous_hash = blockchain.hash(last_block)
    block = blockchain.new_block(proof, previous_hash)
    
    return templates.TemplateResponse("index.html", {
        "request": request,
        "mined_block": block
    })

@app.post('/transactions/new', response_class=HTMLResponse)
async def new_transaction(request: Request, sender: str = Form(...), recipient: str = Form(...), amount: int = Form(...)):
    index = blockchain.new_transaction(sender, recipient, amount)
    transaction_message = f'Transaction will be added to Block {index}'
    
    return templates.TemplateResponse("index.html", {
        "request": request,
        "transaction_message": transaction_message
    })

@app.get('/chain', response_class=HTMLResponse)
async def full_chain(request: Request):
    response = {
        'chain': blockchain.chain,
        'length': len(blockchain.chain),
    }
    return templates.TemplateResponse("index.html", {
        "request": request,
        "chain": json.dumps(response, indent=2)
    })

@app.post('/nodes/register', response_class=HTMLResponse)
async def register_nodes(request: Request):
    try:
        values = await request.json()
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON format")

    nodes = values.get('nodes')
    if nodes is None:
        raise HTTPException(status_code=400, detail="Please supply a valid list of nodes")

    for node in nodes:
        blockchain.register_node(node)

    response = {
        'message': 'New nodes have been added',
        'total_nodes': list(blockchain.nodes),
    }
    return templates.TemplateResponse("index.html", {
        "request": request,
        "node_message": response['message'],
        "total_nodes": response['total_nodes']
    })

@app.get('/nodes/resolve', response_class=HTMLResponse)
async def consensus(request: Request):
    replaced = blockchain.resolve_conflicts()
    if replaced:
        response = {
            'message': 'Our chain was replaced',
            'new_chain': blockchain.chain
        }
    else:
        response = {
            'message': 'Our chain is authoritative',
            'chain': blockchain.chain
        }
    return templates.TemplateResponse("index.html", {
        "request": request,
        "consensus_message": response['message'],
        "chain": json.dumps(response.get('new_chain', response['chain']), indent=2)
    })

if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='127.0.0.1', port=5000)