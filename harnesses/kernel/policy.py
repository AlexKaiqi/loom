"""Reference policy: model-controlled file projection, Pi-owned local loop."""
import json
from pathlib import Path
from projection import project, ProjectionError, PROMPT


class Kernel:
    def __init__(self, harness):
        self.config = json.loads((Path(harness) / 'policy.json').read_text())
        if set(self.config) != {'max_turns', 'timeout', 'max_output_tokens'} or any(type(n) is not int or n <= 0 for n in self.config.values()):
            raise ValueError('invalid reference policy configuration')

    def start(self, params):
        return {**project(params), 'options': {'maxTokens': min(self.config['max_output_tokens'], params.get('model_semantics', {}).get('maxTokens', self.config['max_output_tokens']))},
                'max_turns': self.config['max_turns'], 'timeout': self.config['timeout']}

    @staticmethod
    def continuation(params):
        return params['turn']['message'].get('stopReason') == 'toolUse'

    def prepare(self, params):
        try:
            return project(params)
        except ProjectionError as error:
            turn = params.get('turn')
            if not turn or params.get('repair_attempts', 0) >= 1:
                raise
            context = turn.get('context')
            if not isinstance(context, dict) or not isinstance(context.get('messages'), list):
                raise
            # One explicit repair request may use the last actual closed native
            # exchange. It cannot dispatch business tools, change selection or
            # silently pretend that the invalid candidate has taken effect.
            diagnostic = str(error)
            return {'context': {'systemPrompt': PROMPT, 'messages': [*context['messages'], {
                'role': 'user', 'timestamp': 0,
                'content': '[Context repair only; candidate projection was rejected. Business execution is disabled.]\n'
                           + diagnostic[:8192] + '\nUse Work Bash to repair surface/main.md. The candidate files remain unchanged.'}]},
                'execution_mode': 'context_repair', 'diagnostic': diagnostic,
                'previous_projection_ref': params['previous_projection_ref'],
                'selection': {'status': 'rejected'}, 'sources': []}
