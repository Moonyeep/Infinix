---
name: infinix-testing-debugging
description: Diagnóstico de bugs, falhas de teste e regressões por reprodução controlada. Use quando o usuário relatar erro, comportamento inesperado ou solicitar validação de software.
---

# Testes e depuração

1. Registre o sintoma exato, ambiente, versão e passos mínimos para reproduzir. Separe observação do que ainda é hipótese.
2. Leia logs e código relevante antes de alterar. Evite executar novamente ações que possam produzir efeitos externos ou duplicados.
3. Isole a camada responsável: entrada, lógica, integração, ambiente, rede ou estado persistente. Use dados sintéticos e ambientes descartáveis quando houver risco.
4. Crie uma regressão que falhe antes da correção quando razoável. Corrija a causa raiz, não apenas a mensagem ou o teste.
5. Execute testes direcionados e, se possível, a suíte completa. Informe claramente dependências indisponíveis, testes ignorados e resultados não reproduzidos.
6. Não use dados reais sensíveis em fixtures nem envie logs com segredos. Redija tokens, senhas, cookies e dados pessoais.
7. Verifique que a solução não ampliou permissões, efeitos colaterais ou escopo; relate qualquer incerteza restante.
