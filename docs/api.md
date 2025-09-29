# API pública

## Pipeline de Gestão da Base

### `POST /api/pipeline/start`
Inicia a execução da pipeline de Gestão da Base. A resposta possui status `202 Accepted`
quando a solicitação é aceita. O corpo de resposta descreve o estado atual da execução.

#### Corpo da requisição
```json
{}
```
Opcionalmente é possível informar `"senha"` com a credencial do terminal.

#### Corpo da resposta
```json
{
  "status": "running",
  "started_at": "2024-09-29T15:00:00.000000+00:00",
  "finished_at": null,
  "message": "Execução iniciada"
}
```

### `GET /api/pipeline/state`
Retorna o último estado conhecido da pipeline. Os campos seguem o mesmo formato
utilizado na resposta do `POST /api/pipeline/start`.
