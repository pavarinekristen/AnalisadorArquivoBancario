# Conferência de Pagamentos

Confere o relatório de pagamentos (Excel ou lista colada) contra os arquivos do banco Santander
(CNAB 240: `MOV`, `CRI`, `Retorno`) e diz, para cada favorecido, se foi **pago**, **devolvido**,
**rejeitado**, **aceito e ainda não pago** ou **não enviado**. Gera a mensagem pronta para o chefe.

Roda no seu computador, sem internet e de graça. Os arquivos não saem da sua máquina.

## Instalar (uma vez só)
1. Ter o Python instalado: https://www.python.org/downloads/ (marcar **"Add python.exe to PATH"**).
2. Dar dois cliques em **`instalar.bat`**.

## Usar
1. Dois cliques em **`Conferir.bat`** (ou no atalho da área de trabalho). Abre uma página no navegador.

**Jeito mais rápido (copiar e colar):** no Explorer, selecione o Excel e todos os arquivos do banco
(ou a pasta inteira), aperte **Ctrl+C**, volte na página e clique em **📋 Colar arquivos copiados**.
O Excel vira o relatório e o resto vira os arquivos do banco. Depois é só clicar em **CONFERIR**.

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

A busca é pelo nº do documento; se não tiver, pelo CPF/CNPJ + valor; por último, pelo nome + valor
(nesse caso aparece o aviso "confira").

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
