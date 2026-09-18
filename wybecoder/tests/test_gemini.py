# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

from langchain_google_genai import ChatGoogleGenerativeAI


# models tested:
# gemini-2.5-pro
# gemini-3-flash-preview
# gemini-3-pro-preview
LLM = ChatGoogleGenerativeAI(model="gemini-3-flash-preview", temperature=0.2)


def main():
    for animal in ["dolphin"]:  # , "kangoroo", "duck", "elephant", "ant"]:
        answer = LLM.invoke(f"tell me 5 fun facts about {animal}s").content
        print(answer)


if __name__ == "__main__":
    main()
