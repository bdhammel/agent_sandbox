
"""
[
  {
    "parts": [
      {
        "content": "pw=42",
        "timestamp": "2025-10-24T02:46:38.564081Z",
        "part_kind": "user-prompt"
      }
    ],
    "instructions": null,
    "kind": "request"
  },
  {
    "parts": [
      {
        "tool_name": "secret_plan",
        "args": "{\"password\":42}",
        "tool_call_id": "call_8vnYkl9oL2oW09LaWsgvQFoM",
        "id": null,
        "part_kind": "tool-call"
      }
    ],
    "usage": {
      "input_tokens": 50,
      "cache_write_tokens": 0,
      "cache_read_tokens": 0,
      "output_tokens": 14,
      "input_audio_tokens": 0,
      "cache_audio_read_tokens": 0,
      "output_audio_tokens": 0,
      "details": {
        "accepted_prediction_tokens": 0,
        "audio_tokens": 0,
        "reasoning_tokens": 0,
        "rejected_prediction_tokens": 0
      }
    },
    "model_name": "gpt-4o-mini-2024-07-18",
    "timestamp": "2025-10-24T02:46:37Z",
    "kind": "response",
    "provider_name": "openai",
    "provider_details": {
      "finish_reason": "tool_calls"
    },
    "provider_response_id": "chatcmpl-CU273cUPnJQKMnNQoK00SW7oteSdG",
    "finish_reason": "tool_call"
  },
  {
    "parts": [
      {
        "tool_name": "secret_plan",
        "content": "The secret plan is revealed.",
        "tool_call_id": "call_8vnYkl9oL2oW09LaWsgvQFoM",
        "metadata": [
          {
            "type": "STATE_SNAPSHOT",
            "timestamp": null,
            "raw_event": null,
            "snapshot": {
              "does_the_user_know": true
            }
          },
          {
            "type": "CUSTOM",
            "timestamp": null,
            "raw_event": null,
            "name": "secret_plan",
            "value": [
              "collect underpants",
              "?",
              "profit!"
            ]
          }
        ],
        "timestamp": "2025-10-24T02:46:37.689718Z",
        "part_kind": "tool-return"
      }
    ],
    "instructions": "Be helpful!",
    "kind": "request"
  },
  {
    "parts": [
      {
        "content": "The secret plan has been revealed! If you need any details or have further questions about it, feel free to ask.",
        "id": null,
        "part_kind": "text"
      }
    ],
    "usage": {
      "input_tokens": 78,
      "cache_write_tokens": 0,
      "cache_read_tokens": 0,
      "output_tokens": 25,
      "input_audio_tokens": 0,
      "cache_audio_read_tokens": 0,
      "output_audio_tokens": 0,
      "details": {
        "accepted_prediction_tokens": 0,
        "audio_tokens": 0,
        "reasoning_tokens": 0,
        "rejected_prediction_tokens": 0
      }
    },
    "model_name": "gpt-4o-mini-2024-07-18",
    "timestamp": "2025-10-24T02:46:37Z",
    "kind": "response",
    "provider_name": "openai",
    "provider_details": {
      "finish_reason": "stop"
    },
    "provider_response_id": "chatcmpl-CU273OuDMBD9CLae0uEOsFzHgCA7R",
    "finish_reason": "stop"
  }
]
"""
"""
[
  {
    "id": "e8a35d78-f0df-47de-82bc-a774ab2f972f",
    "role": "user",
    "content": "pw=42"
  },
  {
    "id": "e263cd27-9201-49e3-8c04-2ff79f63ea44",
    "role": "assistant",
    "toolCalls": [
      {
        "id": "call_8vnYkl9oL2oW09LaWsgvQFoM",
        "type": "function",
        "function": {
          "name": "secret_plan",
          "arguments": "{\"password\":42}"
        }
      }
    ]
  },
  {
    "id": "03d66774-c557-44dd-821e-dff5ab16f427",
    "toolCallId": "call_8vnYkl9oL2oW09LaWsgvQFoM",
    "role": "event",
    "content": {
        "type": "STATE_SNAPSHOT",
        "snapshot": { ... }
    }
  },
  {
    "id": "03d66774-c557-44dd-821e-dff5ab16f427",
    "toolCallId": "call_8vnYkl9oL2oW09LaWsgvQFoM",
    "role": "event",
    "content": {
        "type": "CUSTOM",
        "name": "secret_plan",
        "value": [
          "collect underpants",
          "?",
          "profit!"
        ]
    }
  },
  {
    "id": "03d66774-c557-44dd-821e-dff5ab16f427",
    "toolCallId": "call_8vnYkl9oL2oW09LaWsgvQFoM",
    "role": "tool",
    "content": "The secret plan is revealed."
  },
  {
    "id": "d9fe4898-524d-4a4e-b3ad-5fe9460635f5",
    "role": "assistant",
    "content": "The secret plan has been revealed! If you need any details or have further questions about it, feel free to ask."
  }
]
"""
