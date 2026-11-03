"""The ERC-8183 simulation against the pinned specification text: every transition, every role."""
import itertools
import unittest

from prospektor.acp import AgenticCommerce
from prospektor.chain import ZERO, Chain, Contract, Revert, TestToken
from prospektor.secp256k1 import address_of, demo_private_key, public_key

R32 = "0x" + "ab" * 32


def addr(label):
    return address_of(public_key(demo_private_key(label)))


CLIENT, PROVIDER, EVALUATOR, STRANGER, DEPLOYER, TREASURY = map(
    addr, ("t-client", "t-provider", "t-evaluator", "t-stranger", "t-deployer", "t-treasury"))
BUDGET = 1_000


class Hook(Contract):
    def __init__(self, chain, address, behaviour="ok", acp=None):
        super().__init__(chain, address)
        self.behaviour, self.acp = behaviour, acp
        self.s["calls"] = []

    def beforeAction(self, job_id, selector, data):
        self.s["calls"].append(("before", selector))
        if self.behaviour == "revert-all":
            raise Revert("HookSaysNo")
        if self.behaviour == "reenter" and selector == "submit":
            self.call(self.acp, "complete", job_id, R32)

    def afterAction(self, job_id, selector, data):
        self.s["calls"].append(("after", selector))
        if self.behaviour == "revert-after-complete" and selector == "complete":
            raise Revert("RollMeBack")


class EscrowCase(unittest.TestCase):
    mode = "spec"

    def setUp(self):
        self.c = Chain()
        self.token = self.c.deploy(TestToken, DEPLOYER, minter=DEPLOYER)
        self.acp = self.c.deploy(AgenticCommerce, DEPLOYER, self.token, TREASURY, mode=self.mode)
        self.c.send(DEPLOYER, self.token, "mint", CLIENT, 1000 * BUDGET)
        self.c.send(CLIENT, self.token, "approve", self.acp.address, 1000 * BUDGET)

    def job(self, state="Open", hook=ZERO, provider=PROVIDER, expires=86400):
        j = self.c.send(CLIENT, self.acp, "createJob", provider, EVALUATOR, self.c.timestamp + expires, "d", hook)
        if state == "Open":
            return j
        if provider == ZERO:
            self.c.send(CLIENT, self.acp, "setProvider", j, PROVIDER)
        self.c.send(CLIENT if self.mode == "spec" else PROVIDER, self.acp, "setBudget", j, BUDGET)
        self.c.send(CLIENT, self.acp, "fund", j, BUDGET)
        if state == "Funded":
            return j
        self.c.send(PROVIDER, self.acp, "submit", j, R32)
        if state == "Submitted":
            return j
        if state == "Completed":
            self.c.send(EVALUATOR, self.acp, "complete", j, R32)
        elif state == "Rejected":
            self.c.send(EVALUATOR, self.acp, "reject", j, R32)
        elif state == "Expired":
            self.c.advance(expires)
            self.c.send(STRANGER, self.acp, "claimRefund", j)
        return j

    def status(self, j):
        return self.acp.getJob(j)["status"]


class TransitionTable(EscrowCase):
    """Exhaustive: each (state, function, caller) either matches the spec's transition list or reverts."""

    ALLOWED = {  # (state, function, caller) -> resulting state, per the specification text
        ("Open", "fund", "client"): "Funded",
        ("Open", "reject", "client"): "Rejected",
        ("Funded", "submit", "provider"): "Submitted",
        ("Funded", "reject", "evaluator"): "Rejected",
        ("Submitted", "complete", "evaluator"): "Completed",
        ("Submitted", "reject", "evaluator"): "Rejected",
    }
    CALLERS = {"client": CLIENT, "provider": PROVIDER, "evaluator": EVALUATOR, "stranger": STRANGER}

    def call(self, fn, j, caller):
        args = {"fund": (j, BUDGET), "submit": (j, R32), "complete": (j, R32), "reject": (j, R32),
                "claimRefund": (j,)}[fn]
        if fn == "fund" and self.status(j) == "Open":
            self.c.send(CLIENT, self.acp, "setBudget", j, BUDGET)
        self.c.send(caller, self.acp, fn, *args)

    def test_table(self):
        states = ("Open", "Funded", "Submitted", "Completed", "Rejected", "Expired")
        fns = ("fund", "submit", "complete", "reject", "claimRefund")
        checked = 0
        for state, fn, who in itertools.product(states, fns, self.CALLERS):
            j = self.job(state)
            before = self.token.balanceOf(self.acp.address)
            expect = self.ALLOWED.get((state, fn, who))
            try:
                self.call(fn, j, self.CALLERS[who])
                outcome = self.status(j)
            except Revert:
                outcome = None
            if fn == "claimRefund" and state in ("Funded", "Submitted"):
                self.assertIsNone(outcome, "claimRefund before expiry must revert")
            else:
                self.assertEqual(outcome, expect, f"{state} {fn} by {who}")
            if outcome is None:
                self.assertEqual(self.token.balanceOf(self.acp.address), before, "revert moved funds")
            checked += 1
        self.assertEqual(checked, 120)

    def test_refund_after_expiry_anyone_but_funds_go_to_client(self):
        for state in ("Funded", "Submitted"):
            j = self.job(state)
            self.c.advance(86400)
            client_before = self.token.balanceOf(CLIENT)
            self.c.send(STRANGER, self.acp, "claimRefund", j)
            self.assertEqual(self.status(j), "Expired")
            self.assertEqual(self.token.balanceOf(CLIENT), client_before + BUDGET)
            self.assertEqual(self.token.balanceOf(STRANGER), 0)


class SpecRules(EscrowCase):
    def test_fund_guards(self):
        j = self.job("Open", provider=ZERO)
        self.c.send(CLIENT, self.acp, "setBudget", j, BUDGET)
        with self.assertRaisesRegex(Revert, "ProviderNotSet"):
            self.c.send(CLIENT, self.acp, "fund", j, BUDGET)
        self.c.send(CLIENT, self.acp, "setProvider", j, PROVIDER)
        with self.assertRaisesRegex(Revert, "WrongStatus"):
            self.c.send(CLIENT, self.acp, "setProvider", j, STRANGER)
        with self.assertRaisesRegex(Revert, "BudgetMismatch"):
            self.c.send(CLIENT, self.acp, "fund", j, BUDGET + 1)
        j2 = self.job("Open")
        with self.assertRaisesRegex(Revert, "ZeroBudget"):
            self.c.send(CLIENT, self.acp, "fund", j2, 0)

    def test_create_guards(self):
        with self.assertRaisesRegex(Revert, "ZeroAddress"):
            self.c.send(CLIENT, self.acp, "createJob", PROVIDER, ZERO, self.c.timestamp + 10, "d", ZERO)
        with self.assertRaisesRegex(Revert, "ExpiryNotInFuture"):
            self.c.send(CLIENT, self.acp, "createJob", PROVIDER, EVALUATOR, self.c.timestamp, "d", ZERO)

    def test_front_running_budget_is_blocked(self):
        j = self.job("Open")
        self.c.send(CLIENT, self.acp, "setBudget", j, BUDGET)
        self.c.send(PROVIDER, self.acp, "setBudget", j, 9 * BUDGET)  # lands before the client's fund()
        with self.assertRaisesRegex(Revert, "BudgetMismatch"):
            self.c.send(CLIENT, self.acp, "fund", j, BUDGET)

    def test_fees_only_on_completion(self):
        acp = self.c.deploy(AgenticCommerce, DEPLOYER, self.token, TREASURY, platform_fee_bp=250)
        self.c.send(CLIENT, self.token, "approve", acp.address, 10 * BUDGET)
        for end in ("complete", "reject"):
            j = self.c.send(CLIENT, acp, "createJob", PROVIDER, EVALUATOR, self.c.timestamp + 999, "d", ZERO)
            self.c.send(CLIENT, acp, "setBudget", j, BUDGET)
            self.c.send(CLIENT, acp, "fund", j, BUDGET)
            self.c.send(PROVIDER, acp, "submit", j, R32)
            self.c.send(EVALUATOR, acp, end, j, R32)
        self.assertEqual(self.token.balanceOf(TREASURY), 25)
        self.assertEqual(self.token.balanceOf(PROVIDER), BUDGET - 25)

    def test_hook_can_block_actions_but_never_refunds(self):
        hook = self.c.deploy(Hook, DEPLOYER, "ok")
        j = self.job("Funded", hook=hook.address)
        hook.behaviour = "revert-all"
        with self.assertRaisesRegex(Revert, "HookSaysNo"):
            self.c.send(PROVIDER, self.acp, "submit", j, R32)
        self.c.advance(86400)
        self.c.send(STRANGER, self.acp, "claimRefund", j)  # not hookable
        self.assertEqual(self.status(j), "Expired")

    def test_after_hook_revert_rolls_back_payment(self):
        hook = self.c.deploy(Hook, DEPLOYER, "revert-after-complete")
        j = self.job("Submitted", hook=hook.address)
        with self.assertRaisesRegex(Revert, "RollMeBack"):
            self.c.send(EVALUATOR, self.acp, "complete", j, R32)
        self.assertEqual(self.status(j), "Submitted")
        self.assertEqual(self.token.balanceOf(PROVIDER), 0)
        self.assertEqual(self.token.balanceOf(self.acp.address), BUDGET)

    def test_reentrancy_blocked(self):
        hook = self.c.deploy(Hook, DEPLOYER, "reenter")
        j = self.job("Funded", hook=hook.address)
        hook.acp = self.acp
        with self.assertRaisesRegex(Revert, "Reentrancy"):
            self.c.send(PROVIDER, self.acp, "submit", j, R32)

    def test_single_submission(self):
        j = self.job("Submitted")
        with self.assertRaisesRegex(Revert, "WrongStatus"):
            self.c.send(PROVIDER, self.acp, "submit", j, "0x" + "cd" * 32)


class ReferenceModeDeviations(EscrowCase):
    """What changes if the embedded reference AgenticCommerce.sol is deployed instead of the text."""
    mode = "reference"

    def test_budget_front_run_succeeds_against_reference_code(self):
        j = self.job("Open")
        self.c.send(PROVIDER, self.acp, "setBudget", j, BUDGET)
        self.c.send(PROVIDER, self.acp, "setBudget", j, 9 * BUDGET)
        self.c.send(CLIENT, self.acp, "fund", j)  # no expectedBudget parameter
        self.assertEqual(self.acp.getJob(j)["budget"], 9 * BUDGET)
        self.assertEqual(self.token.balanceOf(self.acp.address), 9 * BUDGET)

    def test_client_cannot_set_budget_in_reference_code(self):
        j = self.job("Open")
        with self.assertRaisesRegex(Revert, "Unauthorized"):
            self.c.send(CLIENT, self.acp, "setBudget", j, BUDGET)

    def test_zero_budget_submit_from_open(self):
        j = self.job("Open")
        self.c.send(PROVIDER, self.acp, "submit", j, R32)
        self.assertEqual(self.status(j), "Submitted")

    def test_minimum_expiry(self):
        with self.assertRaisesRegex(Revert, "ExpiryTooShort"):
            self.c.send(CLIENT, self.acp, "createJob", PROVIDER, EVALUATOR, self.c.timestamp + 299, "d", ZERO)

    def test_evaluator_fee_pays_only_on_approval(self):
        acp = self.c.deploy(AgenticCommerce, DEPLOYER, self.token, TREASURY, mode="reference", evaluator_fee_bp=500)
        self.c.send(CLIENT, self.token, "approve", acp.address, 10 * BUDGET)
        earned = {}
        for end in ("complete", "reject"):
            before = self.token.balanceOf(EVALUATOR)
            j = self.c.send(CLIENT, acp, "createJob", PROVIDER, EVALUATOR, self.c.timestamp + 999, "d", ZERO)
            self.c.send(PROVIDER, acp, "setBudget", j, BUDGET)
            self.c.send(CLIENT, acp, "fund", j)
            self.c.send(PROVIDER, acp, "submit", j, R32)
            self.c.send(EVALUATOR, acp, end, j, R32)
            earned[end] = self.token.balanceOf(EVALUATOR) - before
        self.assertEqual(earned, {"complete": 50, "reject": 0})  # an incentive to approve


if __name__ == "__main__":
    unittest.main()
