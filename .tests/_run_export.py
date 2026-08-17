import json
import urllib.request

URL = "http://127.0.0.1:7842/mcp"


def run(code):
    body = {"jsonrpc": "2.0", "id": 1, "method": "execute_python", "params": {"code": code}}
    req = urllib.request.Request(URL, data=json.dumps(body).encode(), method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("Accept", "application/json")
    with urllib.request.urlopen(req, timeout=60) as r:
        resp = json.loads(r.read().decode())
    inner = resp["result"]["result"]
    if not inner.get("success"):
        raise RuntimeError(inner.get("error") + "\n" + inner.get("traceback", ""))
    return inner


# Make the Cube (with Golden HexaMarble) active, then run the export operator with a context override.
CODE = r"""
obj = None
for o in bpy.data.objects:
    for sl in o.material_slots:
        if sl.material and sl.material.name == "Golden HexaMarble":
            obj = o
            break
    if obj:
        break
bpy.context.view_layer.objects.active = obj
mat = bpy.data.materials["Golden HexaMarble"]
obj.active_material = mat
path = "D:\\mat_x\\Golden_HexaMarble_LIVE.mtlx"
res = {"op": None, "err": None}
try:
    with bpy.context.temp_override(object=obj, active_object=obj, material=mat, selected_objects=[obj]):
        res["op"] = bpy.ops.materialx.export(filepath=path)
except Exception as e:
    res["err"] = repr(e)
result = res
"""
out = run(CODE)
print("EXPORT CALL:", out["result"])
print("STDOUT:", out.get("output", "")[:1500])
