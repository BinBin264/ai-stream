# OpenAI Integration

Current code does not call OpenAI yet. The scaffold intentionally uses local
Vietnamese rule parsing first so commerce can work without a provider key.

Provider boundary to implement:

```text
extractIntent
generateReply
createEmbedding
moderate
synthesizeSpeech
```

Rules:

- AI output is a proposal, not an executor.
- AI must never mutate inventory, price, payment, refund, shipment, or order
  completion state.
- Price and stock must come from the commerce database.
- Use `OPENAI_STORE_RESPONSES=false` unless a retention policy is approved.
- Use a hashed viewer identifier as the safety identifier.
