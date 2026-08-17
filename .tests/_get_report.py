import urllib.request, json, ast
URL="http://127.0.0.1:7842/mcp"
def run(code):
    body={"jsonrpc":"2.0","id":1,"method":"execute_python","params":{"code":code}}
    req=urllib.request.Request(URL,data=json.dumps(body).encode(),method="POST")
    req.add_header("Content-Type","application/json");req.add_header("Accept","application/json")
    with urllib.request.urlopen(req,timeout=30) as r: return json.loads(r.read().decode())["result"]["result"]
r = run("result = bpy.context.scene.materialx_last_export_result")
print("RESULT JSON:", r["result"][:3000])
