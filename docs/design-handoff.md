# Handoff: Ecrã de família para Kindle (horizontal, 800×600)

## Novidades e alterações (leia primeiro)

**Novo**
- **M7 · Notícias com várias histórias**: ecrã horizontal com 1 notícia principal (título grande, resumo, QR 88px) + 3 breves. Usado só em dias de notícias importantes; no dia normal mantém-se M2.
- **Variação horizontal 800×600** (M1–M6), com colunas separadas por filete grosso: destaque na coluna larga, apoio na estreita.
- **Letras modernas**: Bricolage Grotesque (títulos/números) + Instrument Sans (corpo/etiquetas), em vez das serifas das direções verticais.
- **Iconografia meteorológica**: sol, nuvem, chuva, vento, trovoada, nascer do sol. Só meteorologia, sempre ao lado de texto.
- **Ícones nas previsões de M2**: "Hoje" (nuvem com chuva) e "Amanhã" (nuvem), 34px, ao lado das temperaturas. Aplicar o mesmo padrão a qualquer previsão por dia.
- **Layouts 8 (Citação) e 9 (Noite)** acrescentados ao sistema; "três itens" e "eventos próximos" fundidos em **Lista ordenada**.
- **Pessoas = distintivos com inicial** (Pedro quadrado cheio, João círculo contorno, Marta círculo cheio, Rui quadrado contorno); substituem avanços e padrões.

**Corrigido**
- M3: coluna da hora alargada (≈2.9× o tamanho da hora) para o distintivo da inicial não se sobrepor à hora.
- M7: altura da grelha 370px e tamanhos de texto ajustados (título 40px, breves 24px) para não colidir com o rodapé.
- Tipografia do M2: "17°" a 200px com ícone de chuva 96px; sem corte de texto.

**Conhecido / por fazer**
- Layout 5 (Foto + legenda) não foi desenhado na variação horizontal.
- Conteúdos, locais e versículo são exemplos; confirmar tradução bíblica.
- Confirmar resolução nativa do Kindle e escalar.

## Overview
Ecrã de informação familiar para um Kindle antigo (e-ink, ~6", monocromático). O Kindle é só o cliente de visualização. Um serviço em Debian, na rede local, recolhe dados, ordena o que importa, **renderiza cada ecrã como imagem** e envia-a ao Kindle. Esta entrega cobre a **variação horizontal moderna (secção 2a)** do ficheiro de design: 6 ecrãs M1–M6.

Princípio: o sistema é adaptativo. Não há caixas fixas por categoria; o servidor escolhe 1 layout e 1–3 itens com pontuação de prioridade (alerta crítico > meteorologia/trânsito invulgar > calendário familiar > notícias importantes > ambiente).

## About the Design Files
Os ficheiros neste pacote são **referências de design em HTML**: protótipos do aspeto pretendido, não código de produção. A tarefa é **recriar estes ecrãs no renderizador do servidor** (sugestão: HTML/CSS + Chromium headless/Playwright → PNG, ou Python/Pillow/Cairo), usando os padrões existentes no projeto. Se não houver ambiente, recomenda-se HTML/CSS + Playwright, porque o desenho já está nesse formato.

Abrir `Kindle Family Display - Directions.dc.html` num browser; a secção **2a** (topo da página) contém M1–M6. As outras secções (1a–1d, verticais) são exploração anterior.

## Fidelity
**Alta fidelidade** para estrutura, tipografia, tamanhos e ícones. Os conteúdos são de exemplo (nomes, locais, versículo, notícia). A tradução do versículo tem de ser confirmada (Bíblia católica em português).

## Hardware / saída
- Canvas **800×600 px**, orientação horizontal (Kindle rodado 90°). Confirmar a resolução nativa do modelo (muitos 6" são 600×800 em vertical; 758×1024 no Paperwhite) e escalar.
- Saída: PNG em **escala de cinzentos de 8 bits (ou 4 bits)**, sem alfa, sem anti-aliasing colorido (sem subpixel).
- Sem animações, sem cor. Texto sem tramado (dither). Só fotos são tramadas a 4 níveis.
- Atualização completa do painel ao alternar entre ecrã normal e invertido (alerta) para evitar fantasmas.
- Botões físicos anterior/seguinte: ordem fixa 1 Notícias·Tempo → 2 Família → 3 Agenda. Num Kindle horizontal os botões ficam em baixo/lado; a ordem mantém-se.
- Mínimos: texto de leitura ≥ 20 px; etiquetas em maiúsculas ≥ 16 px; traço mínimo 2 px.

## Design Tokens
Cores (apenas cinzentos):
- Papel `#f1f0ec` (branco quente); Tinta `#0c0c0c`.
- Invertido (alerta): fundo `#0c0c0c`, texto `#f1f0ec`.
- Sem outros tons no texto/UI. Foto: 4 níveis.

Tipografia (Google Fonts; incluir os ficheiros localmente no servidor):
- **Títulos/números:** Bricolage Grotesque, pesos 600/700/800, `letter-spacing` −0.02 a −0.06em conforme o tamanho.
- **Corpo/etiquetas:** Instrument Sans 400/500/600.
- Etiquetas: 16px, maiúsculas, `letter-spacing .12em`, peso 600.

Escala usada: 17° hero 200px/0.8; título alerta 120px/0.88; hora 54px; quilómetros 96px; hero família 98px/0.92; título secundário 34–40px; corpo 20–26px.

Geometria: margens do ecrã 26px (vertical) × 40px (horizontal). Cabeçalho: hora à esquerda (54px), data à direita (24px, 600), filete inferior 4px. Colunas separadas por filete de 3px. Filetes internos 2px. Rodapé a 18px da base: nome do ecrã à esquerda, paginação à direita (■ □ □), 16px.

## Layouts (sistema)
O servidor escolhe entre layouts; todos partilham o cabeçalho (hora + data sempre visíveis).
1. **Destaque** – um item, ecrã inteiro.
2. **Destaque + secundário** – coluna larga (≈1.4fr) + estreita (1fr). M1.
3. **Lista ordenada** – 3 itens; altura/tamanho = prioridade. M6 (eventos próximos).
4. **Alerta** – invertido; causa à esquerda (1.5fr), dados à direita (1fr). M4.
5. **Foto + legenda** – sangrada ou emoldurada, hora sobreposta (não desenhada em M1–M6).
6. **Notícia + QR** – coluna direita de M2; QR 88px no canto inferior direito.
7. **Agenda** – hoje | amanhã em duas colunas (1.15fr / 1fr). M3.
8. **Citação** – versículo, curiosidade, mensagem. M5.
9. **Noite** – primeiro evento de amanhã + uma linha de tempo; menor taxa de atualização.

## Screens / Views

### M1 · Família · manhã (destaque + secundário)
- Cabeçalho: `07:35` / `Seg 5 Out`.
- Grelha 2 colunas `1.4fr 1fr`, altura 380px, margem superior 26px; filete vertical 3px entre colunas.
- Esquerda (padding-right 30px): etiqueta `PEDRO · 08:30`; título 98px "Visita de estudo"; texto 24px "Autocarro no portão principal. Lanche e impermeável."
- Direita (padding-left 30px, gap 22px): `JOÃO · 09:30` + "Dentista" 40px; filete 2px; `LEMBRETE` + "Assinar a autorização do Pedro" 26px/600.
- Faixa inferior (filete 2px topo): ícone chuva 34px + "Chuva forte depois das 17:00 · 14° / 19°" 26px/600.
- Rodapé: `FAMÍLIA` · `■ □ □`.

### M2 · Notícias / Meteorologia · dia normal
- Esquerda (padding-right 28px, filete 3px): `17°` 200px + ícone chuva 96px; "Nublado. Chuva depois das 17:00" 30px/600; em baixo, filete 2px e duas células: `HOJE 14° / 19°`, `AMANHÃ 12° / 17°` (22px).
- Direita (padding-left 28px): `PORTUGAL · PÚBLICO`; título 38px/1.05; resumo 21px (máx. 1–2 linhas, gerado por IA); em baixo ícone nascer do sol + `07:21 – 18:58` (20px) e **QR 88×88** com margem branca.
- Notícias: 0–2 histórias; o QR abre sempre a fonte original.
- Rodapé: `NOTÍCIAS · TEMPO` · `□ □ ■`.

### M3 · Agenda · hoje | amanhã
- Colunas `1.15fr 1fr`, altura 400px. Etiqueta `HOJE` / `AMANHÃ · TER 6`.
- Cada evento: linha com filete superior 2px; hora (Bricolage) + distintivo da pessoa + título. **Tamanho por importância**: 34/28/22px (hora) e +4px no título; peso 700 se >30px, senão 600.
- Hoje: 08:30 Visita de estudo (P), 09:30 Dentista (J), 18:00 Levantar encomenda (M). Amanhã: 08:30 Natação (P), 19:00 Reunião de pais (R).
- Legenda de pessoas no canto inferior direito (16px).
- **Pessoas = distintivo com inicial, 19px** (Bricolage): Pedro quadrado cheio, João círculo contorno, Marta círculo cheio, Rui quadrado contorno (classes `.pg.P/.J/.M/.R` no ficheiro). Sempre iguais em qualquer tamanho; sem cor.

### M4 · Alerta · chuva forte (invertido)
- Fundo `#0c0c0c`, texto `#f1f0ec`. Cabeçalho `16:12` / `Seg 5 Out`.
- Esquerda (1.5fr): etiqueta `AVISO METEOROLÓGICO · NÍVEL 2 DE 3`; ícone chuva 120px; "Chuva forte" 120px/0.88 em duas linhas.
- Direita (1fr, filete 3px claro): `DAS` 17:00 (70px), `ÀS` 23:00 (70px), `PREVISÃO` 30–45 mm (40px).
- Fundo (a 30px da base): filete 2px + "Saia mais cedo para ir buscar as crianças. Recolha a roupa." 26px/600.
- Tom calmo: palavras simples, sem ícone de emergência, sem pisca.

### M5 · Família · calmo · versículo
- Cabeçalho `21:05` / `Dom 4 Out`.
- Aspas “ de 200px (coluna 90px) + texto 72px/1.02: "O Senhor é o meu pastor: nada me faltará." Referência 20px, maiúsculas: `SL 23 (22), 1 · 27.º DOMINGO DO TEMPO COMUM`.
- Aparece quando não há conteúdo de prioridade superior. Alternativa: foto do dia (layout 5).

### M6 · Fim de semana · eventos próximos
- Cabeçalho `10:15` / `Sáb 10 Out`. Linha: `A MENOS DE 25 KM · HOJE` + ícone sol + "Seco até às 18:00 · 15° / 21°" (22px/600).
- 3 colunas iguais, altura 370px, filetes verticais 3px. Cada uma: distância 96px + "km" 24px; título 34px; local·hora 20px; QR 80px opcional (só no primeiro).
- Exemplos: 8 km Mercado de produtores (Cascais, até às 13:00); 17 km Oficina de barro para crianças (Museu de Sintra, 10:30); 23 km Festa das vindimas (Palmela, todo o dia).

### M7 · Notícias · várias histórias
- Cabeçalho `12:40` / `Seg 5 Out`. Grelha `1.2fr 1fr`, altura 400px.
- Esquerda (padding-right 30px, filete 3px): fonte (etiqueta), título 54px/1, resumo 23px, QR 88px em baixo à direita com texto "Ler no telemóvel".
- Direita (padding-left 30px): 3 breves empilhadas separadas por filete 2px: fonte (etiqueta), título 30px/1.05, linha de resumo 20px. Sem QR nas breves; máximo 1 principal + 3 breves.
- Rodapé: `NOTÍCIAS · 4 HISTÓRIAS` · `■ □ □`. Usado só em dias de notícias importantes; no dia normal mantém-se M2 (0–2 histórias).

## Iconografia
Só meteorologia, sempre à frente de texto, nunca sozinhos. SVG 64×64, `stroke-width 4`, linhas arredondadas, nuvem preenchida em `currentColor`. Conjunto: sol (círculo r11 + 8 raios), nuvem, chuva (nuvem + 3 traços), vento, trovoada, nascer do sol. Sem ícones para pessoas, eventos e notícias. Fonte: desenhados neste projeto (SVG inline no HTML).

## Interactions & Behavior
- Sem interação no ecrã. Navegação por botões físicos do Kindle; o cliente pede ao servidor o ecrã seguinte/anterior (ou o servidor empurra a sequência).
- **Alertas** (tempo severo, trânsito, alteração de calendário, encerramento de escola, transportes) substituem temporariamente o ecrã de topo, sem alterar a ordem dos botões.
- **Viagem**: 3 dias antes, contagem decrescente, tempo no destino, estado do voo e perturbações sobem de prioridade nos ecrãs existentes (sem ecrã próprio).
- **Modos por hora**: manhã (tempo + primeiros compromissos + lembrete), dia de trabalho (mini-secção pessoal: próxima reunião, prioridade, alerta; **nunca** em área familiar), noite (layout 9, mínimo), fim de semana (eventos a ≤25 km, normalmente a partir de sexta à tarde).
- Regras da Família: sem compras; aniversários de família e amigos próximos; escola só se importante; contagem só do próximo evento importante; foto quando há pouco conteúdo; versículo quando falta conteúdo prioritário; curiosidades rotativas (ciência, natureza, história, geografia, tecnologia, espaço).

## State Management (servidor)
- Contrato por ecrã: `{ layout: nome, items: [{ tipo, prioridade, dados, privado? }] }` com 1–3 itens.
- O renderizador ajusta o texto ao layout e **elimina o item de menor prioridade** em vez de descer abaixo do tamanho mínimo.
- Itens privados (trabalho) só renderizam se o dispositivo estiver marcado como local pessoal.
- Atualização: baixa frequência (p. ex. 1–5 min no dia, 15–30 min à noite); atualização completa em transições normal↔invertido.
- Fontes de dados: calendário familiar, meteorologia (UV, pólen, qualidade do ar), notícias (PT + eventos mundiais), eventos locais, voos/trânsito, versículos, fotos.

## Assets
Sem imagens. Fontes: Bricolage Grotesque e Instrument Sans (Google Fonts, licença OFL). QR: gerar no servidor (nível de correção M, módulo ≥ 3 px, margem branca de 4 módulos).

## Files
- `Kindle Family Display - Directions.dc.html` — design de referência (secção 2a = esta entrega; 1a–1d = exploração vertical anterior; inclui comparação e sistema recomendado).
- `support.js` — runtime necessário para abrir o ficheiro.
