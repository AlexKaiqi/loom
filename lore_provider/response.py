"""Strict saved-wire to complete Pi assistant data; no tool or final actions."""
import hashlib
from .jsoncodec import WireError, require, strict_load
from .request import MODEL, shell_args


def unsigned(value):
    require(type(value) is int and value>=0)
    return value


def usage(raw):
    require(isinstance(raw, dict))
    prompt, completion, total = (unsigned(raw[key]) for key in ("prompt_tokens", "completion_tokens", "total_tokens"))
    require(total==prompt+completion)
    prompt_detail, output_detail = raw.get("prompt_tokens_details", {}), raw.get("completion_tokens_details", {})
    require(isinstance(prompt_detail, dict) and isinstance(output_detail, dict))
    for value in list(prompt_detail.values())+list(output_detail.values()): unsigned(value)
    read = unsigned(prompt_detail.get("cached_tokens", 0))
    write = unsigned(prompt_detail.get("cache_write_tokens", 0))
    require(read+write<=prompt)
    result = dict(input=prompt-read-write,output=completion,cacheRead=read,cacheWrite=write,totalTokens=total,
                  cost=dict(input=0,output=0,cacheRead=0,cacheWrite=0,total=0))
    if "reasoning_tokens" in output_detail:
        result["reasoning"] = unsigned(output_detail["reasoning_tokens"])
        require(result["reasoning"]<=completion)
    return result


def content(message, finish):
    require(isinstance(message, dict) and message.get("role")=="assistant")
    require(message.get("refusal") in (None, ""))
    calls = message.get("tool_calls", [])
    if "content" not in message:
        require(finish in ("tool_calls", "length") and isinstance(calls, list) and bool(calls))
    value = message.get("content")
    require(value is None or isinstance(value, str))
    output = [] if value is None else [dict(type="text",text=value)]
    require(isinstance(calls, list))
    seen = set()
    for call in calls:
        require(isinstance(call, dict) and call.get("type")=="function")
        call_id, function = call["id"], call["function"]
        require(isinstance(call_id, str) and call_id and call_id not in seen)
        seen.add(call_id)
        require(isinstance(function, dict) and function.get("name")=="shell" and isinstance(function.get("arguments"), str))
        arguments = strict_load(function["arguments"])
        require(isinstance(arguments, dict))
        shell_args(arguments)
        output.append(dict(type="toolCall",id=call_id,name=function["name"],arguments=arguments))
    require(output)
    require(finish!="stop" or not calls)
    require(finish!="tool_calls" or bool(calls))
    return output


def normalize(raw, transport):
    require(transport["complete"], "incomplete_transport")
    require(transport["http_status"]==200, "http_error")
    require(len(raw)<=1048576)
    try:
        body = strict_load(raw)
        require(isinstance(body, dict) and body.get("object")=="chat.completion")
        require(body.get("model")==MODEL, "model_mismatch")
        require(isinstance(body.get("id"), str) and body["id"])
        created = unsigned(body["created"])
        choices = body["choices"]
        require(isinstance(choices, list) and len(choices)==1 and isinstance(choices[0], dict))
        choice = choices[0]
        require(type(choice.get("index")) is int and choice["index"]==0)
        finish = choice["finish_reason"]
        require(isinstance(finish, str) and finish)
        require(finish in ("stop", "tool_calls", "length"), "unsupported_finish_reason")
        normalized_usage = usage(body["usage"])
        message = dict(role="assistant", content=content(choice["message"],finish),api="lore-proxy-completions",
                       provider="lore-authorized-proxy",model=body["model"],responseId=body["id"],timestamp=created*1000,
                       rawStopReason=finish,stopReason={"stop":"stop","tool_calls":"toolUse","length":"length"}[finish],
                       usage=normalized_usage)
        wire = dict(sha256=hashlib.sha256(raw).hexdigest(),size=len(raw),http_status=transport["http_status"],
                    response_id=body["id"],raw_stop_reason=finish,raw_usage=body["usage"])
        return dict(message=message,wire=wire,pricing=dict(status="UNKNOWN",currency=None,actual_cost=None))
    except (KeyError, ValueError, TypeError, RecursionError) as error:
        raise WireError("invalid_wire") from error
