# Conferência de Pagamentos

Confere o relatório de pagamentos (Excel ou lista colada) contra os arquivos do banco e diz, para cada
favorecido, se foi **pago**, **devolvido**, **rejeitado**, **aceito e ainda não pago** ou **não enviado**.
Gera a mensagem pronta para o chefe.

Bancos atendidos (escolha no topo da tela **Conferir**):
- **Santander** (033): CNAB 240 `MOV`, `CRI`, `Retorno` (ex: `FORN_EZN1_06_071026P_MOV.TXT`).
  Rede: `\\Ntedi020\grpaftdata$\INBOXENV` (retorno) e `SENTBOX` (remessa). UCM: `tranap$/santander$/inbox$/processed$`.
- **Tribanco** (634): CNAB 240, retorno `.dat` (ex: `A35708191410260001.dat`), com a crítica (`BD`/erros) e o
  pagamento (`00`)/devolução (`Z...`) no mesmo tipo de arquivo. Rede: `\\ntedi020\AFTData\tranap\tribanco`.
  UCM: `tranap$/tribanco$/retorno$` (com subpastas `processed$`/`error$`). O arquivo é reconhecido pelo header (banco 634), e a data/hora de
  geração do header define a ordem entre retornos.

Arquivos de outro banco são ignorados com aviso (ex: colar MOV do Santander com o Tribanco selecionado).

Roda no seu computador, sem internet e de graça. Os arquivos não saem da sua máquina.

## Instalar (uma vez só)
1. Ter o Python instalado: https://www.python.org/downloads/ (marcar **"Add python.exe to PATH"**).
2. Dar dois cliques em **`instalar.bat`**.

## Usar
1. Dois cliques em **`Conferir.bat`** (ou no atalho da área de trabalho). Abre uma página no navegador.

**Jeito mais rápido (copiar e colar):** no Explorer, selecione o Excel e todos os arquivos do banco
(ou a pasta inteira), aperte **Ctrl+C**, volte na página e clique em **📋 Colar arquivos copiados**.
O Excel vira o relatório e o resto vira os arquivos do banco. Depois é só clicar em **CONFERIR**.

**Quem conferir:** escolha uma das três formas:
- **Digitar nomes** (padrão): um favorecido por linha. Pode ser nome inteiro ou parte, CPF/CNPJ ou nº do
  documento. Para filtrar, acrescente valor (`6.503,00`) e/ou data (`07/10/2026`) na mesma linha.
  O programa acha o nome mesmo abreviado ou cortado pelo banco (ex: `FULANO DE TAL DA SILVA` acha `F T DA SILVA`)
  e mostra **todos** os pagamentos daquele favorecido nos arquivos, cada um com seu código.
- **Excel** do relatório (abas BANCO, RESUMO ou SISTEMA).
- **Colar lista do sistema** (texto "Situação: Com Erro").

Ou, informando separado:

2. **Relatório:** arraste o Excel (ex: `RELATÓRIO COMPLETO 05-10.xlsx`) e escolha a lista
   (relatório do banco, resumo ou não pagos do sistema). Ou escolha "Colar lista" e cole o texto do sistema.
3. **Arquivos do banco:** arraste **todos** os arquivos da pasta (Ctrl+A na pasta e arraste),
   ou escolha "Pasta" e cole o caminho (ex: `C:\Users\krist\Downloads\arquivos\FINAL24`).
4. Clique em **CONFERIR**.
5. Copie a mensagem no ícone de copiar da caixa. Se quiser, exporte o resultado em Excel.

> Mande sempre a pasta inteira. Se faltar o MOV com a devolução, o programa vai mostrar "pago".
> Ele avisa quando falta algum lote na sequência (ex: tem 01 e 03, falta 02).

## Como ele decide
| Situação nos arquivos | Resultado |
|---|---|
| MOV com `00`/`03` (e nada depois) | Pago |
| MOV com código começando com `Z` (ZA, ZAZ7, ZAAE...) ou `XD` | Devolução (mesmo se teve `00` antes) |
| CRI ou MOV com código de erro (AG, AE, HF...) | Rejeitado pelo banco |
| CRI com `BD`, sem MOV | Aceito, ainda não pago |
| Favorecido aparece, mas com outro valor/documento | Outro pagamento |
| Não aparece em nenhum arquivo | Não enviado |

No **Tribanco** o retorno faz os dois papéis: registro com `00`/`03` ou `Z...`/`XD` conta como MOV,
o resto (`BD`, códigos de erro) conta como CRI. Ex: `BD` num retorno e `00` num retorno seguinte = Pago.

A busca é pelo nº do documento; se não tiver, pelo CPF/CNPJ + valor; por último, pelo nome + valor
(nesse caso aparece o aviso "confira").

## Reprocessar
Página **Reprocessar**: lista os arquivos do `INBOXENV\<subpasta>` (filtro por data e nome), você marca
quais e o programa move para `\\Ntedi020\grpaftdata$\INBOX\<subpasta>`, onde são processados de novo.
Primeiro **Simular** (mostra o que vai acontecer), depois confirmar e **Mover agora**. Nunca sobrescreve:
se o arquivo já existe no INBOX ele fica onde está, com aviso. Tudo que foi movido fica registrado no
Histórico. Tribanco: falta configurar o destino (`BASE_TRIBANCO_INBOX` em `conferencia/reprocessar.py`).

## Personalizar
- **`regras/ocorrencias.yaml`**: tabela de códigos (FEBRABAN completa + códigos do Santander Z7/Z8/Z9).
  Para incluir um código novo, acrescente uma linha.
- **`regras/mensagens.yaml`**: texto das mensagens pro chefe.

## Histórico
Toda conferência fica salva em `dados/historico.db`. Na aba **Histórico** dá para buscar por nome,
CPF/CNPJ ou documento e ver quem já teve mais de uma devolução. O programa também avisa quando
um favorecido da conferência atual já foi devolvido antes.

## Para quem for mexer no código
```
.venv\Scripts\python -m pytest
```
`conferencia/cnab240.py` lê os arquivos do banco · `relatorio.py` lê o Excel/lista ·
`motor.py` cruza e classifica · `mensagem.py` monta o texto · `historico.py` grava no SQLite ·
`app.py` é a tela (Streamlit).
