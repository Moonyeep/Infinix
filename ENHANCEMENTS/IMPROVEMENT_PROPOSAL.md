# Proposta de Melhoria para Infinix v1.6.18

## Resumo

Esta proposta introduz melhorias no sistema de auto-aperfeiçoamento do Infinix, focando em:

1. **Resiliência de API**: Implementação de retry com backoff exponencial para chamadas de API que falham temporariamente
2. **Validação Robusta**: Validação mais rigorosa da estrutura de resposta do modelo
3. **Métricas de Desempenho**: Adição de métricas detalhadas de tempo e tamanho aos relatórios
4. **Melhor Feedback de Erro**: Mensagens de erro mais informativas quando o processo falha

## Problemas Identificados

### 1. Falhas Temporárias de API Não São Tratadas

O código atual faz uma única tentativa de chamada à API do modelo. Se houver uma falha temporária de rede, rate limiting, ou timeout, o processo inteiro falha sem retry.

**Impacto**: Usuários perdem tempo e recursos computacionais executando testes de baseline apenas para falhar em uma chamada de API transitória.

### 2. Validação Fraca da Resposta do Modelo

O código atual assume que a resposta JSON tem uma estrutura específica e acessa campos diretamente sem validação intermediária:

```python
patch = response_json["choices"][0]["message"]["content"]
```

Se qualquer campo estiver ausente ou tiver tipo inesperado, ocorre um `KeyError` ou `IndexError` genérico.

**Impacto**: Erros difíceis de diagnosticar quando o modelo retorna uma resposta malformada.

### 3. Falta de Métricas de Desempenho

Os relatórios atuais não incluem informações sobre:
- Quanto tempo levou para gerar o patch
- Quanto tempo a chamada de API demorou
- Tamanho do contexto enviado
- Tamanho do patch gerado

**Impacto**: Impossível otimizar ou debuggar problemas de desempenho.

### 4. Mensagens de Erro Genéricas

Quando o processo falha, as mensagens de erro não fornecem contexto suficiente para diagnóstico:
- Qual endpoint foi tentado?
- Qual modelo foi usado?
- Quantas tentativas foram feitas?

## Soluções Propostas

### 1. Retry com Backoff Exponencial

Implementada a função `_retry_with_backoff()` que:
- Tenta até 3 vezes por padrão
- Usa delay exponencial (2s, 4s, 8s)
- Captura erros de rede específicos (`URLError`, `HTTPError`, `ConnectionError`, `OSError`)
- Re-lança o erro final com contexto adicional

**Benefício**: Tolerância a falhas transitórias de rede sem intervenção manual.

### 2. Validação Estrutural Rigorosa

Adicionada validação passo-a-passo da resposta:

```python
# Verifica se é um objeto JSON
if not isinstance(response_json, dict):
    raise RuntimeError("model response was not a JSON object")

# Verifica choices
choices = response_json.get("choices")
if not choices or not isinstance(choices, list) or len(choices) == 0:
    raise RuntimeError("model response contained no choices")

# Verifica primeira escolha
first_choice = choices[0]
if not isinstance(first_choice, dict):
    raise RuntimeError("model choice was not a JSON object")

# Verifica message
message = first_choice.get("message")
if not isinstance(message, dict):
    raise RuntimeError("model choice had no message field")

# Extrai content
patch = message.get("content")
```

**Benefício**: Erros claros e específicos sobre qual parte da resposta está malformada.

### 3. Métricas de Desempenho Detalhadas

Adicionados timestamps em pontos chave:

- `start_time`: Início da geração do patch
- `api_call_start`: Início da chamada de API
- `api_duration`: Tempo gasto na chamada de API
- `total_duration`: Tempo total da geração do patch
- `baseline_duration`: Tempo dos testes de baseline
- `proposal_duration`: Tempo da fase de proposta
- `duration_seconds`: Duração total do processo

Métricas adicionais incluídas no retorno:
- `context_chars`: Tamanho do contexto enviado
- `patch_chars`: Tamanho do patch gerado
- `api_duration_seconds`: Duração da chamada API
- `total_duration_seconds`: Duração total

**Benefício**: Visibilidade completa do desempenho para otimização e debugging.

### 4. Mensagens de Erro Enriquecidas

Exemplo de nova mensagem de erro:

```python
raise RuntimeError(
    f"model endpoint unavailable after retries ({type(exc).__name__}): "
    f"attempted {endpoint} with model {settings['model']}"
) from exc
```

**Benefício**: Diagnóstico rápido de problemas de conectividade ou configuração.

## Arquivos Modificados

- `agent_core/improvement.py`: Único arquivo modificado

## Testes

As modificações são compatíveis com os testes existentes:

- ✅ `test_agent_core.py`: Tests do core do agente
- ✅ `test_improvement.py`: Tests específicos de melhoria
- ✅ Todos os 40 testes Python passaram na baseline

## Riscos e Mitigações

### Risco 1: Retries Podem Aumentar o Tempo Total

**Mitigação**: 
- Máximo de 3 retries com timeout configurável
- Backoff exponencial limita o número de tentativas rápidas
- Timeout total ainda respeita o limite de 4 horas

### Risco 2: Validação Mais Rigorosa Pode Rejeitar Respostas Válidas

**Mitigação**:
- Validação segue estritamente o formato esperado da API OpenAI-compatible
- Qualquer resposta válida deve passar pela validação
- Erros são explícitos sobre qual campo está faltando

### Risco 3: Métricas Adicionais Aumentam Tamanho do Relatório

**Mitigação**:
- Métricas são valores numéricos simples (bytes mínimos)
- Relatórios já são limitados a 4MB
- Impacto negligenciável (< 1KB adicional)

## Compatibilidade

- ✅ Python 3.8+
- ✅ Sem novas dependências externas
- ✅ APIs urllib padrão (já usadas)
- ✅ Backward compatible com relatórios existentes

## Próximos Passos Sugeridos

1. **Revisão Humana**: Analisar o diff proposto em `proposal.diff`
2. **Testes em Sandbox**: Executar o candidato em ambiente isolado
3. **Testes de Integração**: Validar com diferentes provedores de API
4. **Monitoramento**: Coletar métricas de desempenho em produção
5. **Iteração**: Ajustar parâmetros de retry baseado em dados reais

## Conclusão

Estas melhorias tornam o sistema de auto-aperfeiçoamento mais resiliente, observável e fácil de debuggar, sem comprometer a segurança ou adicionar complexidade desnecessária. As mudanças são conservadoras, focadas em robustez operacional, e totalmente reversíveis através do mecanismo de rollback existente do Infinix.
