token_store = {
    "primary": None,
    "fallback": None
}


def set_token(agent_type: str, token: str):
    token_store[agent_type] = token


def get_token(agent_type: str):
    return token_store.get(agent_type)