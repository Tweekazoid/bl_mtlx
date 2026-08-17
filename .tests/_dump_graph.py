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
    'm = bpy.data.materials["Golden HexaMarble"]\n'
    "nt = m.node_tree\n"
    "result = {\n"
    '  "nodes": [(n.name, n.type, n.bl_idname,\n'
    "             [s.name for s in n.outputs],\n"
    "             [(s.name, s.is_linked) for s in n.inputs]) for n in nt.nodes],\n"
    '  "links": [(l.from_node.name, l.from_socket.name, l.to_node.name, l.to_socket.name)\n'
    "            for l in nt.links],\n"
    "}\n"
)

data = ast.literal_eval(run(CODE))
print("NODES:", len(data["nodes"]), " LINKS:", len(data["links"]))
print("\n== NODES ==")
for name, typ, idname, outs, ins in data["nodes"]:
    print(f"- {name}  [{typ}]  outs={outs}")
print("\n== LINKS ==")
for fn, fs, tn, ts in data["links"]:
    print(f"{fn}.{fs} -> {tn}.{ts}")
