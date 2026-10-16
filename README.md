# Conferência de Pagamentos

Confere o relatório de pagamentos (Excel, lista colada ou nomes digitados) contra os arquivos do banco e diz,
para cada favorecido, se foi **pago**, **devolvido**, **rejeitado**, **aceito e ainda não pago**,
**não enviado** ou se precisa **verificar**. Gera um resumo técnico pronto para copiar.

Bancos atendidos (escolha no topo da tela **Conferir**):
- **Santander** (033): CNAB 240 `MOV`, `CRI`, `Retorno` (ex: `FORN_EZN1_06_071026P_MOV.TXT`).
- **Tribanco** (634): CNAB 240, retorno `.dat` (ex: `A35708191410260001.dat`), com a crítica (`BD`/erros) e o
  pagamento (`00`)/devolução (`Z...`) no mesmo tipo de arquivo. O arquivo é reconhecido pelo header (banco 634),
  e a data/hora de geração do header define a ordem entre retornos.

Arquivos de outro banco são ignorados com aviso (ex: colar MOV do Santander com o Tribanco selecionado).

Roda no computador de quem usa: a tela só abre na própria máquina (`127.0.0.1`) e os arquivos não saem dela.
Só a página **Arquivos UCM** conversa com a nuvem (Oracle UCM/OIC do cliente).

## Instalar (uma vez só)
**Com o instalador** (`ConferenciaPagamentos-2.0.0.exe`): próximo, próximo, concluir. Não precisa de internet
nem de Python; cria o atalho na área de trabalho.

**Sem o instalador:**
1. Ter o Python 3.11 ou mais novo: https://www.python.org/downloads/ (marcar **"Add python.exe to PATH"**).
2. Dar dois cliques em **`instalar.bat`** (com a pasta `wheels\` ao lado, instala sem internet).
3. Preencher **`config/cliente.yaml`** (o instalar.bat cria a partir de `config/cliente.exemplo.yaml`).

## Configurar o cliente (`config/cliente.yaml`)
Tudo que muda de uma empresa para outra fica nesse arquivo (ele não vai para o git):
- `pastas`: pastas de rede do retorno, remessa, Tribanco e INBOX (destino do Reprocessar).
- `pastas_permitidas`: onde o "Caminho manual" pode ler (fora delas a tela recusa).
- `documento`: prefixo e tamanho do nº do documento (padrão `10000` + 15 dígitos).
- `excel`: textos que identificam as abas do relatório.
- `ucm`: endereços do OIC/IDCS e as **contas UCM liberadas** (só elas podem ser consultadas).
- `bancos_ativos`, `marca` (nome e logo), `retencao_dias` (LGPD).

A credencial do UCM (client_id/secret) **não** fica em arquivo: é gravada no cofre do Windows pela própria
página Arquivos UCM ("Configurar credencial").

## Usar
1. Dois cliques em **`Conferir.bat`** (ou no atalho da área de trabalho). Abre uma página no navegador.

**Jeito mais rápido (copiar e colar):** no Explorer, selecione o Excel e todos os arquivos do banco
(ou a pasta inteira), aperte **Ctrl+C**, volte na página e clique em **Colar arquivos copiados**.
O Excel vira o relatório e o resto vira os arquivos do banco. Depois é só clicar em **CONFERIR**.

**Quem conferir:** escolha uma das três formas:
- **Digitar nomes** (padrão): um favorecido por linha. Pode ser nome inteiro ou parte, CPF/CNPJ ou nº do
  documento. Para filtrar, acrescente valor (`6.503,00`, `6503` ou `6.503`) e/ou data (`07/10/2026`).
  O programa acha o nome mesmo abreviado ou cortado pelo banco (ex: `FULANO DE TAL DA SILVA` acha `F T DA SILVA`)
  e mostra **todos** os pagamentos daquele favorecido nos arquivos, cada um com seu código.
  Também acha pela empresa pagadora (nome com 2 palavras ou mais, ou o CNPJ).
- **Excel** do relatório (abas BANCO, RESUMO ou SISTEMA).
- **Colar lista do sistema** (texto "Situação: Com Erro").

**Arquivos do banco:** pasta padrão da rede (com período De/Até, que já começa na data mais antiga do
relatório), arrastar os arquivos ou caminho manual (só pastas liberadas).

Clique em **CONFERIR**, copie o resumo no ícone da caixa e, se quiser, exporte o resultado em Excel.

> Mande sempre a pasta inteira. Se faltar o MOV com a devolução, o programa vai mostrar "pago".
> Ele avisa quando falta algum lote na sequência (ex: tem 01 e 03, falta 02), quando um arquivo tem linha fora
> do padrão de 240 caracteres e quando um arquivo do banco não tem nenhum pagamento.

## Como ele decide
Vale o **último registro que decide** (pago ou devolução), em ordem de data, lote e hora do arquivo.

| Situação nos arquivos | Resultado |
|---|---|
| MOV com `00`/`03` (e nenhuma devolução depois) | Pago |
| Primeiro código começando com `Z` (`ZA`, `ZAZ7`, `ZAAE`, `ZAZ9`... qualquer complemento) ou `XD` | Devolução (mesmo se teve `00` antes) |
| CRI ou MOV com código de erro cadastrado (AG, AE, HF...) e nenhum pago/devolução | Rejeitado pelo banco |
| CRI/MOV com `BD` (aceito), sem pago | Aceito, ainda não pago |
| Código não cadastrado (sem `Z` na frente), `BF` (excluído) ou sem código | **Verificar** (nunca vira "Rejeitado" sem certeza) |
| Favorecido aparece, mas com outro valor/documento | Outro pagamento |
| Não aparece em nenhum arquivo | Não enviado |

Depois do pago/devolução, o que vier sem decidir (ex: `BD`, ou CRI rejeitado num reenvio) não muda o status: vira aviso.

No **Tribanco** o retorno faz os dois papéis: registro com `00`/`03` ou `Z...`/`XD` conta como MOV,
o resto (`BD`, códigos de erro) conta como CRI. Ex: `BD` num retorno e `00` num retorno seguinte = Pago.

A busca é pelo nº do documento. Se o documento do relatório não estiver nos arquivos, tenta CPF/CNPJ + valor
+ data (aviso "confira"). Sem documento: CPF/CNPJ + valor; por último, nome + valor (aviso "confira").
Pelo nome, aceita abreviado ou cortado pelo banco (`F T DA SILVA`), mas não aceita palavra sobrando no
nome do banco (`JOSE DA SILVA` não casa com `JOSE DA SILVA SANTOS`).

## Layout CNAB 240 suportado
- Segmento **A** (crédito em conta, TED/DOC) com o **B** (CPF/CNPJ do favorecido).
- Segmento **J** (boleto) com o **J-52** (CPF/CNPJ do beneficiário).
- Ocorrências nas posições 231-240 (até 5 códigos de 2 caracteres).
- Arquivo com ou sem quebra de linha, em latin-1 ou UTF-8.

**Ainda não suportado:** segmentos **N** e **O** (tributos e concessionárias) e Pix com segmento B de chave.
Esses pagamentos aparecem como "Não enviado". Para incluir, é preciso um arquivo de exemplo de cada banco.

## Reprocessar
Página **Reprocessar**: lista os arquivos da pasta de retorno (`<retorno>\<subpasta>`, filtro por data e nome),
você marca quais e o programa move para `<inbox>\<subpasta>`, onde são processados de novo.
Primeiro **Simular** (mostra o que vai acontecer), depois confirmar e **Mover agora**. Nunca sobrescreve:
se o arquivo já existe no INBOX ele fica onde está, com aviso. Tudo que foi movido fica registrado no
Histórico, com o usuário do Windows que moveu. Tribanco: configurar `pastas.tribanco_inbox`.

## Personalizar
- **`regras/ocorrencias.yaml`**: tabela de códigos (FEBRABAN completa + códigos do Santander Z7/Z8/Z9).
  Para incluir um código novo, acrescente uma linha (vale na hora, sem reiniciar).

## Histórico
Toda conferência fica salva em `dados/historico.db`. Na aba **Histórico** dá para buscar por nome,
CPF/CNPJ ou documento e ver quem já teve mais de uma devolução. O programa também avisa quando
um favorecido da conferência atual já foi devolvido antes (pelo CPF/CNPJ; pelo nome só quando falta CPF).

## LGPD
- **O que fica guardado:** nome, CPF/CNPJ, documento, valor, data, status e arquivo de cada favorecido
  conferido, em `dados/historico.db`, só na máquina de quem usa. Também o usuário do Windows que conferiu/moveu.
- **Por quanto tempo:** `retencao_dias` (padrão 365). Ao abrir, o programa apaga o que for mais antigo.
  Na aba Histórico dá para apagar antes ("Apagar histórico antigo").
- **Na tela e no Excel exportado** o CPF/CNPJ aparece mascarado (`***223330001**`); "Mostrar CPF/CNPJ completos"
  libera e fica registrado no log.
- **Log** (`dados/logs/app.log`): registra conferências, movimentações e erros, sempre com CPF/CNPJ mascarado.

## Suporte
Página **Sobre**: versão, configuração carregada e **Exportar diagnóstico** (zip com o log mascarado e a
configuração, sem senhas).

## Para quem for mexer no código
```
.venv\Scripts\python -m pip install -r requirements-dev.txt
.venv\Scripts\python -m pytest
```
- `conferencia/cnab240.py` lê os arquivos do banco · `bancos/` tem o que é próprio de cada banco ·
  `relatorio.py` lê o Excel/lista · `motor.py` cruza e classifica · `mensagem.py` monta o resumo ·
  `historico.py` grava no SQLite · `config.py` lê a configuração do cliente · `log.py` · `credenciais.py`.
- `telas/` são as páginas (Streamlit); `app.py` só monta a navegação.
- Banco novo: um módulo em `conferencia/bancos/` seguindo `PerfilBanco` e registrado em `REGISTRO`.
- Os testes do caso real usam `tests/dados/` (anonimizado por `tests/ferramentas/anonimizar.py`).
- Instalador: `instalador\gerar_pacote.bat` e depois compilar `instalador\setup.iss` no Inno Setup 6.
