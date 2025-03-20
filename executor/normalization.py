# tfg_bot_trading/executor/normalization.py

# Diccionario con mapeos de claves erróneas a las correctas (en minúsculas)
NORMALIZATION_MAPPING = {
    "ipliplier": "multiplier",
    # Agrega aquí otros mapeos de errores tipográficos si fuese necesario
}

def normalize_strategy_params(params: dict) -> dict:
    """
    Normaliza las claves de los parámetros de una estrategia.
    Para cada clave en el diccionario, si existe una entrada en NORMALIZATION_MAPPING
    (comparando en minúsculas), se reemplaza por la clave normalizada.
    """
    normalized = {}
    for key, value in params.items():
        new_key = NORMALIZATION_MAPPING.get(key.lower(), key)
        normalized[new_key] = value
    return normalized

# Nuevo diccionario para normalizar valores de acción (en minúsculas)
ACTION_NORMALIZATION_MAPPING = {
    "__strategy": "STRATEGY"
    # Agrega aquí otros mapeos de errores tipográficos si fuese necesario
}

def normalize_action(action: str) -> str:
    """
    Normaliza el valor de una acción.
    Si la acción se encuentra en ACTION_NORMALIZATION_MAPPING (comparando en minúsculas),
    se devuelve su valor normalizado. De lo contrario, se retorna la acción original.
    """
    return ACTION_NORMALIZATION_MAPPING.get(action.lower(), action)
