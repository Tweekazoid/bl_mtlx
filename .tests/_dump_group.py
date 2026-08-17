import ast
import json
import urllib.request

URL = "http://127.0.0.1:7842/mcp"


def run(code):
    body = {"jsonrpc": "2.0", "id": 1, "method": "execute_python", "params": {"code": code}}
    req = urllib.request.Request(URL, data=json.dumps(body).encode(), method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("Accept", "application/json")
    with urllib.request.urlopen(req, timeout=30) as r:
        resp = json.loads(r.read().decode())
    inner = resp["result"]["result"]
    if not inner.get("success"):
        raise RuntimeError(inner.get("error") + "\n" + inner.get("traceback", ""))
    return inner["result"]


CODE = (
    'g = bpy.data.materials["Golden HexaMarble"].node_tree.nodes["Hex-Marble"]\n'
    "nt = g.node_tree\n"
    "result = {\n"
    '  "tree": nt.name,\n'
    '  "nodes": [(n.name, n.type,\n'
    "             [s.name for s in n.outputs],\n"
    "             [(s.name, s.is_linked) for s in n.inputs]) for n in nt.nodes],\n"
    '  "links": [(l.from_node.name, l.from_socket.name, l.to_node.name, l.to_socket.name)\n'
    "            for l in nt.links],\n"
    "}\n"
)

data = ast.literal_eval(run(CODE))
print("GROUP TREE:", data["tree"], " NODES:", len(data["nodes"]), " LINKS:", len(data["links"]))
print("\n== NODES ==")
for name, typ, outs, ins in data["nodes"]:
    linked_ins = [i[0] for i in ins if i[1]]
    print(f"- {name}  [{typ}]  outs={outs}  linkedIns={linked_ins}")
print("\n== LINKS ==")
for fn, fs, tn, ts in data["links"]:
    print(f"{fn}.{fs} -> {tn}.{ts}")
