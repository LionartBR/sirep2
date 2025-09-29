from __future__ import annotations

DATA_LINES = range(10, 20)  # linhas onde estão os dados na E555
COL_START = 1
COL_WIDTH = 80

STATUS_HINT_POS = (21, 45, 21)  # "Linhas x a y de z"
FOOTER_MSG_POS = (22, 1, 80)  # Mensagens "FGEN2213"/"FGEN1389"

POS_E527_NUMERO = (6, 71)
POS_E527_RAZAO = (5, 18, 62)
POS_E527_SALDO = (19, 50, 30)
POS_E527_CNPJ = (4, 37, 18)

POS_E50H_NUMERO = (6, 71)
POS_GRDE = (9, 2, 33)

MAX_ATTEMPTS = 3
REQUEST_DELAY = 0.2

RESOLUCAO_DESCARTAR = "974/20"

MSG_FIM_BLOCO = "FGEN2213"
MSG_ULTIMA_PAGINA = "FGEN1389"

TIPOS_PREDET = [
    "Ação Judicial/Ajuste",
    "Acompanhamento diferenciado",
    "Controle Representação",
    "Em depuração",
    "Erro de encadeamento",
    "Garantido por Dep. Jud.",
    "PROFUT",
    "Regularização de Plano Indevido",
    "Retorno Pré-formalizado",
]
