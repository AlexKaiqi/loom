import { createMessageConnection, StreamMessageReader, StreamMessageWriter, ResponseError } from "vscode-jsonrpc/node";
import { prepare } from "./pi.mjs";
import { runAgent } from "./agent.mjs";

if (Number(process.versions.node.split(".")[0]) !== 24) {
  process.stderr.write("Loom model worker requires Node 24\n");
  process.exit(1);
}
const connection = createMessageConnection(new StreamMessageReader(process.stdin), new StreamMessageWriter(process.stdout));

for (const method of ["model.complete", "agent.run"]) {
  connection.onRequest(method, async (params, token) => {
    const request = await prepare(params, token);
    try {
      if (method === "agent.run") return await runAgent(params, request, connection);
      return await request.api.stream(params.model, params.context, request.options).result();
    } catch (error) {
      if (error instanceof ResponseError) throw error;
      // Provider error messages belong in Pi results; unexpected exceptions must not echo secrets.
      throw new ResponseError(-32000, "Model worker failed; remote outcome may be unknown");
    } finally {
      request.dispose();
    }
  });
}
connection.onClose(() => process.exit(0));
process.stdin.on("end", () => process.exit(0));
connection.listen();
