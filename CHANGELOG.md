# Histórico de versões

## 2.0.0
### Segurança
- A tela só abre na própria máquina (`127.0.0.1`); ninguém da rede/VPN acessa.
- "Caminho manual" só aceita pastas liberadas na configuração; UCM só consulta contas liberadas.
- Credencial do UCM no cofre do Windows (Gerenciador de Credenciais).

### Classificação
- Novo status **Verificar**: código não cadastrado, `BF` (excluído) ou registro sem código nunca viram "Rejeitado".
- Vale o último registro que decide (pago ou devolução); `00` seguido de `BD` continua Pago, com aviso.
- Primeiro código começando com `Z` (ZA, ZAZ7, ZAAE, ZAZ9...) é sempre devolução.
- Busca por nome: nome igual sempre casa; abreviado/truncado casa no modo conferir; palavra sobrando no banco não casa.
- Documento do relatório que não está nos arquivos: tenta CPF/CNPJ + valor + data (com aviso).
- Pesquisa pela empresa pagadora exige 2+ palavras ou o CNPJ.

### Robustez
- Lê CNAB sem quebra de linha e em UTF-8; avisa linha fora de 240 e arquivo sem pagamento.
- Valor "1.500" e "1500" digitados; CPF de 10 dígitos; data inválida não derruba a tela.
- Histórico fecha a conexão, tem migrações versionadas e registra o operador.
- Reprocessar avisa "copiado, mas a origem não foi apagada".
- UCM não repete erro de credencial (4xx).
- Tabela de códigos relida ao editar o YAML.

### Produto
- Configuração por cliente (`config/cliente.yaml`), perfis de banco (`conferencia/bancos/`), log com CPF mascarado,
  LGPD (retenção, expurgo, CPF/CNPJ mascarado na tela e no Excel), página Sobre/Diagnóstico, versões fixas,
  instalador offline, testes com dados anonimizados e CI.
