# Início rápido em português

Instale Docker com Docker Compose no servidor de casa. Depois de clonar, execute
na pasta do projeto. Basta um navegador para experimentar: não é necessário
Kindle, calendário, conta ou chave de API.

```sh
cp config.pt.example.toml config.toml
mkdir -p photos calendars secrets
docker compose up --build -d
```

Abra [notícias e tempo](http://127.0.0.1:8000/kindle/news-weather.png) ou
[família](http://127.0.0.1:8000/kindle/family.png) no servidor.
O exemplo usa português, `Europe/Lisbon`, tempo em **Lisboa** e notícias da
**RTP País**. Sem calendário, a página da família mostra o tempo e uma curiosidade.
O [estado](http://127.0.0.1:8000/api/status) apresenta erros e atualizações.

Para uma demonstração sem Internet, defina `demo_mode = true` em `config.toml`.
A demonstração usa dados fictícios em português e não consulta fontes externas.
A primeira instalação/build do Docker continua a precisar de Internet.
Volte a `false` para dados reais.

Depois de editar, execute `docker compose up -d --force-recreate`.

## Personalizar

- `language = "pt"`, `"en"` ou `"de"` define os textos incluídos na aplicação.
- `country = "PT"`, `"GB"` ou `"DE"` define a rubrica nacional e a relevância
  para a classificação opcional por IA. Idioma, país e fuso horário são independentes.
- Substitua as coordenadas e o nome de Lisboa pela sua localidade. Não existe
  deteção automática de localização.
- Consulte `config.example.toml` para calendários, dimensões e outras opções.
  As notícias, eventos, nomes e legendas próprias mantêm o idioma original.
  Mudar de idioma não altera os feeds configurados.
- A dimensão inicial é 800×600. Para Paperwhite 11 na horizontal, use largura
  1648, altura 1236 e rotação 90.

`config.toml` é privado e ignorado pelo Git. As variáveis de ambiente têm
prioridade. As fontes reais precisam de Internet; uma falha conserva os últimos
dados disponíveis.

## Ligar o Kindle

Defina `BIND_ADDRESS` no ficheiro `.env` com o endereço local do servidor e
reinicie. Mantenha o serviço na rede de casa: não tem autenticação. Siga a
[configuração do Kindle](../README.md#kindle-setup) para KOReader e o plugin TRMNL.

A configuração usa o [RSS da RTP País](https://www.rtp.pt/noticias/rss/pais).
Pode acrescentar outros feeds em `config.toml`: `national` usa o país configurado;
`world` exige `curated = true` ou palavras em `keywords`. Aplicam-se as condições
de utilização de cada fornecedor.

Outras configurações: [English](setup.en.md) · [Deutsch](setup.de.md).
