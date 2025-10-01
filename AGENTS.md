# Diretrizes para agentes na base `sirep2`

## Contexto geral
- Este repositório implementa serviços e APIs do projeto SIREP usando Python 3.10+, FastAPI e uma arquitetura em camadas (domínio, serviços, infraestrutura e UI).
- Utilize sempre anotações de tipo completas em novas funções, métodos e variáveis públicas.
- Prefira imutabilidade (tuplas, dataclasses congeladas) para modelos de domínio quando fizer sentido.
- Nunca adicione artefatos gerados automaticamente (por exemplo, `__pycache__`, arquivos temporários de editor ou dados de teste) ao controle de versão.

## Convenções de código
- Siga PEP 8 para estilo de código Python e mantenha nomes descritivos em inglês (exceto strings exibidas ao usuário final).
- Organize imports padrão/terceiros/projeto com uma linha em branco entre os grupos. Não envolva imports em blocos `try/except`.
- Utilize `async`/`await` quando interagir com APIs assíncronas do FastAPI.
- Sempre valide dados de entrada com Pydantic ou modelos de domínio antes de propagá-los.
- Documente funções e classes com docstrings concisas explicando propósito e contratos.

## Estrutura das camadas
- `domain/`: Regras de negócio e modelos. Não acesse bibliotecas externas de I/O aqui.
- `services/`: Orquestra regras de negócio, pode falar com infra. Dependa de interfaces definidas em `domain`.
- `infra/`: Integrações com bancos de dados, filas, etc. Mantenha configurações via variáveis de ambiente.
- `api/`: Rotas FastAPI e dependências. Delegue lógica aos serviços.
- `ui/`: Aplicação web estática. Alterações visuais exigem captura de tela no PR.
- `tests/`: Utilize `pytest`. Organize fixtures em `conftest.py`.

## Testes e qualidade
- Rode `pytest` antes de submeter alterações que impactem regras de negócio ou API.
- Inclua testes unitários para novos comportamentos e atualize snapshots conforme necessário.
- Ao tocar em código assíncrono, cubra caminhos de sucesso e de erro.
- Sempre que possível valide tipagens com `mypy` e formatação com `ruff` ou `black` antes de abrir um PR.

## Commits e versionamento
- Utilize mensagens de commit curtas e no imperativo descrevendo claramente a alteração principal.
- Evite commits que misturem refatorações e mudanças de comportamento sem justificativa clara.
- Garanta que a branch esteja sincronizada com `main` antes de abrir um novo PR, resolvendo conflitos localmente.

## Documentação
- Atualize `docs/` ao introduzir novos fluxos, endpoints ou comandos.
- Forneça exemplos de uso na documentação sempre que adicionar endpoints ou scripts.

## Mensagens finais e PRs
- No resumo final para o usuário, liste mudanças relevantes e testes executados. Inclua comandos realmente executados e marque-os como ✅/⚠️/❌ conforme o resultado.
- Após commitar, utilize a ferramenta `make_pr` para gerar título e corpo do Pull Request cobrindo o que foi feito e como validar.
- Ao redigir o corpo do PR, liste quaisquer impactos em contratos públicos (APIs, eventos ou esquemas) e passos de rollout se relevantes.

## Scripts úteis
- `uvicorn api.app:create_app --reload` para desenvolvimento local.
- `pytest` para testes automatizados.

Siga estas diretrizes em todas as subpastas, a menos que haja um `AGENTS.md` mais específico.
