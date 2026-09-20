// Pi owns the only active model/tool loop. Loom supplies custody and strategy hooks.
import { runAgentLoopContinue } from "@earendil-works/pi-agent-core";
import { lazyStream } from "@earendil-works/pi-ai";
import { ErrorCodes, ResponseError } from "vscode-jsonrpc/node";
import { apiFor } from "./pi.mjs";

const stableEvents = new Set(["turn_start", "message_end", "turn_end", "agent_end"]);
const publicOptions = new Set([
  "temperature", "maxTokens", "reasoning", "cacheRetention", "transport",
  "thinkingEnabled", "thinkingBudgetTokens", "thinkingDisplay", "effort",
  "toolChoice", "deferred", "thinkingBudgets", "samplingParams", "sessionId",
  "websocketConnectTimeoutMs", "metadata", "maxRetryDelayMs",
]);

export async function runAgent(params, request, connection) {
  if (!Number.isInteger(params.maxTurns) || params.maxTurns <= 0) {
    throw new ResponseError(ErrorCodes.InvalidParams, "maxTurns must be a positive integer");
  }
  let completedTurns = 0;
  let hostFailure;
  const hooks = new Set(params.hooks ?? []);
  const callHost = async (method, payload) => {
    try {
      return await connection.sendRequest(method, payload);
    } catch (error) {
      hostFailure = error;
      request.controller.abort();
      throw error;
    }
  };
  const tools = (params.context.tools ?? []).map((tool) => ({
    ...tool, label: tool.name, replay: "never", executionMode: "sequential",
    execute: async (toolCallId, args, signal) => {
      if (signal?.aborted) throw new Error("Tool dispatch cancelled");
      return callHost("tool.execute", { toolCallId, name: tool.name, arguments: args });
    },
  }));
  const messages = await runAgentLoopContinue(
    { ...params.context, tools },
    {
      ...request.options, model: params.model, convertToLlm: (messages) => messages,
      toolExecution: "sequential",
      shouldStopAfterTurn: async (turn) => {
        await callHost("agent.event", { type: "turn_checkpoint", turn });
        completedTurns += 1;
        if (request.controller.signal.aborted || turn.message.stopReason === "length" || completedTurns >= params.maxTurns) return true;
        return hooks.has("shouldStop") ? Boolean(await callHost("agent.shouldStop", turn)) : false;
      },
      prepareNextTurn: hooks.has("prepareTurn") ? async (turn) => {
        const update = await callHost("agent.prepareTurn", turn);
        // Executable tools remain host capabilities, never serialized functions.
        if (update?.context) update.context = { ...update.context, tools };
        return update ?? undefined;
      } : undefined,
    },
    async (event) => {
      if (stableEvents.has(event.type)) await callHost("agent.event", event);
    },
    request.controller.signal,
    (model, context, options) => lazyStream(model, async () => {
      const { headers: _headers, ...publicModel } = model;
      const nativeContext = { ...context, tools: context.tools?.map(({ name, description, parameters }) => ({ name, description, parameters })) };
      // Custody binds the context after prepareNextTurn, immediately before SDK dispatch.
      await callHost("agent.event", { type: "model_request", model: publicModel, context: nativeContext,
        options: { ...Object.fromEntries(Object.entries(options ?? {}).filter(([key]) => publicOptions.has(key))), maxRetries: 0, timeoutMs: params.timeoutMs } });
      if (request.controller.signal.aborted) throw new Error("Model dispatch cancelled");
      return (await apiFor(model)).streamSimple(model, context, {
        ...options, apiKey: params.apiKey, maxRetries: 0,
        timeoutMs: params.timeoutMs, signal: request.controller.signal,
      });
    }),
  );
  if (hostFailure) throw new ResponseError(-32001, "Host effect or custody callback failed; outcome requires reconciliation");
  return messages;
}
