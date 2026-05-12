from engine.estilos.placeholder import gerar_placeholder


def gerar(localidades: list[dict], opcoes: dict | None = None):
    return gerar_placeholder(localidades, opcoes, "v1d2")
