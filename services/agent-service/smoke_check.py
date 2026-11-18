import anthropic

client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from the environment

message = client.messages.create(
    model="claude-haiku-5-5",
    max_tokens=50,
    messages=[{"role": "user", "content": "Reply with the single word: ready"}],
)

print(message.content[0].text)
print(message.usage)
INPUT_PRICE_PER_MTOK = 0.10   # USD per million input tokens
OUTPUT_PRICE_PER_MTOK = 0.50  # USD per million output tokens

usage = message.usage

cost = (usage.input_tokens * INPUT_PRICE_PER_MTOK
        + usage.output_tokens * OUTPUT_PRICE_PER_MTOK) / 1_000_000
print(f"Estimated cost: ${cost:.8f}")

INPUT_PRICE_PER_MTOK = 0.10   # USD per million input tokens
OUTPUT_PRICE_PER_MTOK = 0.50  # USD per million output tokens

usage = message.usage
cost = (usage.input_tokens * INPUT_PRICE_PER_MTOK
        + usage.output_tokens * OUTPUT_PRICE_PER_MTOK) / 1_000_000
print(f"Estimated cost: ${cost:.8f}")

print("Input tokens:", message.usage.input_tokens)
print("Output tokens:", message.usage.output_tokens)
print("Total tokens:", message.usage.input_tokens + message.usage.output_tokens)