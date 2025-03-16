# tfg_bot_trading/executor/normalization.py

# Diccionario con mapeos de claves erróneas a las correctas (en minúsculas)
NORMALIZATION_MAPPING = {
    "ipliplier": "multiplier",
    # Agrega aquí otros mapeos de errores tipográficos si fuese necesario
    # "mulltiplier": "multiplier",
    # "stratgy": "strategy",
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
