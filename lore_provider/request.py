"""The finite authorized Pi text/function context to fixed completion request."""
from .jsoncodec import WireError, depth, encode, require

MODEL = "gpt-5.6-terra"
SHELL = dict(name="shell", description="Run ordinary Shell in an authorized target",
             parameters=dict(type="object", properties=dict(target=dict(type="string", enum=["runtime", "workspace"]),
                             script=dict(type="string")), required=["target", "script"], additionalProperties=False))
BINDING = {"session_id", "operation_id", "response_entry_id", "input_ref", "harness_ref", "capability_ref"}


def shell_args(args):
    require(isinstance(args, dict) and set(args)=={"target", "script"})
    require(args["target"] in ("runtime", "workspace") and isinstance(args["script"], str))
    depth(args)
    return args


def text_content(content):
    if isinstance(content, str):
        return content
    require(isinstance(content, list))
    parts = []
    for block in content:
        require(isinstance(block, dict) and set(block)=={"type", "text"} and block["type"]=="text" and isinstance(block["text"], str))
        parts.append(block["text"])
    return "".join(parts)


def messages(context):
    require(isinstance(context["systemPrompt"], str))
    original = context["messages"]
    require(isinstance(original, list) and len(original)<=64)
    result = [dict(role="system", content=context["systemPrompt"])]
    pending, seen = {}, set()
    for message in original:
        require(isinstance(message, dict))
        role = message.get("role")
        if role == "user":
            require(set(message)<={"role", "content", "timestamp"})
            result.append(dict(role="user",content=text_content(message["content"])))
        elif role == "assistant":
            # Preserve original tool IDs and block order; no action is invoked here.
            require(set(message)<={"role", "content", "timestamp", "api", "provider", "model", "responseId",
                                           "rawStopReason", "stopReason", "usage", "errorMessage"})
            content = message["content"]
            if isinstance(content, str): content = [dict(type="text",text=content)]
            require(isinstance(content, list))
            text, calls = [], []
            for block in content:
                require(isinstance(block, dict))
                if block.get("type") == "text":
                    require(set(block)=={"type", "text"} and isinstance(block["text"], str))
                    text.append(block["text"])
                else:
                    require(set(block)=={"type", "id", "name", "arguments"} and block["type"]=="toolCall")
                    call_id = block["id"]
                    require(isinstance(call_id, str) and call_id and call_id not in seen and block["name"]=="shell")
                    seen.add(call_id); pending[call_id] = block["name"]
                    calls.append(dict(id=call_id,type="function",function=dict(name=block["name"],
                                      arguments=encode(shell_args(block["arguments"])).decode("utf-8"))))
            value = dict(role="assistant",content="".join(text) if text else None)
            if calls: value["tool_calls"] = calls
            require(text or calls)
            result.append(value)
        elif role == "toolResult":
            require(set(message)<={"role", "toolCallId", "toolName", "content", "isError", "timestamp", "details"})
            call_id = message["toolCallId"]
            require(isinstance(call_id, str) and call_id in pending and pending[call_id]==message["toolName"])
            require(type(message["isError"]) is bool)
            del pending[call_id]
            result.append(dict(role="tool",tool_call_id=call_id,content=text_content(message["content"])))
        else:
            raise WireError("invalid_request")
    require(not pending)
    return result


def encode_request(intent, scope):
    try:
        require(isinstance(intent, dict) and set(intent)=={"binding", "model", "max_completion_tokens", "context"})
        require(isinstance(scope, dict) and set(scope)==BINDING)
        require(encode(intent["binding"])==encode(scope))
        for key in ("session_id", "operation_id", "response_entry_id"):
            require(isinstance(scope[key], str) and scope[key])
        for key in ("input_ref", "harness_ref", "capability_ref"):
            require(isinstance(scope[key], dict) and set(scope[key])=={"id", "sha256"})
            require(isinstance(scope[key]["id"], str) and scope[key]["id"])
            require(isinstance(scope[key]["sha256"], str) and len(scope[key]["sha256"])==64 and
                    all(c in "0123456789abcdef" for c in scope[key]["sha256"]))
        require(intent["model"]==MODEL)
        budget = intent["max_completion_tokens"]
        require(type(budget) is int and 0 < budget <= 2048)
        context = intent["context"]
        require(isinstance(context, dict) and set(context)=={"systemPrompt", "messages", "tools"})
        require(encode(context["tools"])==encode([SHELL]))
        raw = encode(dict(model=MODEL,n=1,stream=False,max_completion_tokens=budget,
                          messages=messages(context),tools=[dict(type="function",function=SHELL)]))
        require(len(raw)<=65536)
        return raw
    except (WireError, KeyError, TypeError, ValueError, UnicodeError, RecursionError) as error:
        raise WireError("invalid_request") from error
