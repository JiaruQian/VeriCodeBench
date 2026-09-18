# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

MODIFIED_HEADER_MESSAGE = """
The code executed successfully, but it did not satisfy the required criteria.  
Please ensure that you either:

1. Use the provided specification header and supply a proof for the corresponding `prove_correct` correctness theorem,  
**OR**
2. Use the provided unsatisfiability theorem header and supply a proof for it.

Do not modify the headers or theorem statements. Choose one approach and provide the appropriate proof.
""".strip()

ADDITIONAL_GUARD_STATEMENTS_MESSAGE = "I noticed that you added guard statements (#guard ...) in the code. Please remove them."
