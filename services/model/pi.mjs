// Dispatch only. Provider wire formats, SDKs and parsing belong to pi-ai.
import { ErrorCodes, ResponseError } from "vscode-jsonrpc/node";

const APIs = new Set([
  "openai-completions", "openai-responses", "openai-codex-responses",
  "azure-openai-responses", "anthropic-messages", "bedrock-converse-stream",
  "google-generative-ai", "google-vertex", "mistral-conversations", "pi-messages",
]);

export function supportsAPI(api) { return APIs.has(api); }

export async function apiFor(model) {
  if (!supportsAPI(model?.api)) throw new Error("Unsupported Pi API");
  return import(`@earendil-works/pi-ai/api/${model.api}`);
}

export async function prepare(params, token) {
  if (params?.protocol_version !== "loom/1" || !supportsAPI(params?.model?.api) ||
      !Array.isArray(params?.context?.messages) ||
      typeof params.apiKey !== "string" || !params.apiKey ||
      !Number.isInteger(params.timeoutMs) || params.timeoutMs <= 0) {
    throw new ResponseError(ErrorCodes.InvalidParams, "Invalid model request or unsupported protocol/API");
  }
  const api = await apiFor(params.model);
  const controller = new AbortController();
  const subscription = token.onCancellationRequested(() => controller.abort());
  if (token.isCancellationRequested) controller.abort();
  const timer = setTimeout(() => controller.abort(), params.timeoutMs);
  return {
    api, controller,
    options: { ...params.options, apiKey: params.apiKey, signal: controller.signal,
      timeoutMs: params.timeoutMs, maxRetries: 0 },
    dispose() { clearTimeout(timer); subscription.dispose(); },
  };
}
