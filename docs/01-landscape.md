# Landscape and positioning

ControlPlane is an allocator above detectors. It should call or wrap existing detectors through `controlplane/detectors/base.py`; it should not claim to replace them.

| Product or layer | What it does | Position relative to ControlPlane |
| --- | --- | --- |
| NVIDIA NeMo Guardrails | Configurable input, retrieval, dialog, execution, and output rails; supports parallel rails and model-backed checks. | Compose. NeMo can supply detector and execution-rail signals; ControlPlane decides which paid checks run under a route budget. |
| Guardrails AI | Python validation framework with reusable validators and corrective actions. | Compose through the detector adapter. It is a validation toolkit, not the economic policy. |
| AWS Bedrock Guardrails | Evaluates prompts and responses with configured policies; includes contextual grounding and Automated Reasoning checks with per-policy charges. | Alternative hosted detector set. ControlPlane's contribution is the cross-policy spend decision and per-route floor. |
| Azure AI Content Safety | Harm classification, Prompt Shields, groundedness detection, and protected-material checks. | External Tier 0/1 signal source. English-only limits on some features must be kept in route policy. |
| Llama Guard / Prompt Guard | Open models for input/output safety classification and prompt-attack detection. | Candidate small-model adapter, especially when data residency rules favour local inference. |
| Lakera Guard / Check Point AI Guardrails | Managed prompt defense, moderation, and leakage prevention. | Security detector option. ControlPlane does not reproduce its classifier. |
| Microsoft Presidio | Rule, checksum, deny-list, NER, and context-based PII detection plus redaction, hashing, masking, and encryption. | Natural Tier 0/1 privacy adapter. The repository ships a regex stub so the offline demo stays small. |
| OpenAI moderation | Hosted moderation classification; the moderation endpoint is free for OpenAI API users. | Useful zero-price safety signal for an OpenAI route, but still not a grounding, privacy, or business-consequence allocator. |
| LiteLLM | OpenAI-shaped multi-provider proxy with authentication hooks, logging, rate limits, and spend tracking. | Gateway neighbour. ControlPlane could be a callback or sidecar rather than another provider router. |
| Portkey | Gateway routing, retries, budgets, observability, and synchronous/asynchronous guardrails. | Closest product overlap. Its budget limits cap usage; our experiment allocates assurance calls using expected avoided loss plus a statistical floor. |
| Bifrost | OpenAI-compatible high-throughput provider gateway with routing, logs, keys, budgets, and guardrails. | Infrastructure layer that could host or precede this policy. Gateway overhead claims are vendor benchmarks and are not used in our business case. |

## Does the positioning survive the evidence?

Yes, with a narrower claim than the Round 1 story implied. NeMo, Bedrock, Azure, Portkey, and Bifrost already combine multiple guardrail stages. Portkey already has gateway budgets and guardrail orchestration. The whitespace is therefore not "a gateway that has budgets." It is a testable allocation policy that prices expected avoided harm, measures checker catch rate, preserves a route risk floor, and exposes the full arithmetic in an audit record.

The latency spread exists, but the prototype treats its exact values as assumptions. The MiniCheck paper reports a 770M fact-checker reaching GPT-4-level benchmark accuracy at roughly 400 times lower cost. Cloud Automated Reasoning and LLM-judge calls are paid, model-backed checks; deterministic rules and small local classifiers are materially cheaper. No source supports one universal millisecond number across hardware and payloads, so our 4 ms, 70 ms, and 900 ms tier latencies are simulator inputs that must be replaced by deployment measurements.

## Primary sources

- [NVIDIA NeMo rail types and parallel configuration](https://docs.nvidia.com/nemo/guardrails/configure-guardrails/yaml-schema/guardrails-configuration)
- [Guardrails AI repository](https://github.com/guardrails-ai/guardrails)
- [Amazon Bedrock Guardrails behavior](https://docs.aws.amazon.com/bedrock/latest/userguide/guardrails-how.html)
- [Amazon Bedrock pricing, including Automated Reasoning](https://aws.amazon.com/bedrock/pricing/)
- [Azure AI Content Safety overview](https://learn.microsoft.com/en-us/azure/ai-services/content-safety/overview)
- [Meta Llama developer resources](https://ai.meta.com/llama/get-started/)
- [Check Point AI Guardrails defenses](https://docs.lakera.ai/docs/defenses)
- [Microsoft Presidio anonymization flow](https://microsoft.github.io/presidio/text_anonymization/)
- [OpenAI moderation endpoint cost](https://help.openai.com/en/articles/4936833-how-to-use-chatgpt)
- [LiteLLM proxy features](https://docs.litellm.ai/)
- [Portkey AI Gateway](https://portkey.ai/docs/product/ai-gateway)
- [Bifrost gateway repository](https://github.com/maximhq/bifrost)

