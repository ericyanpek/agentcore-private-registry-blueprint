# Confounders to rule out before classifying an anomaly

These factors regularly cause **apparent** cost spikes that are not
actually anomalous. Confirm each is not the explanation before
proceeding to Step 2 (Classify).

## RI / SP amortization timing
Reserved Instance / Savings Plan upfront fees are amortized monthly,
but credit application timing can shift line items between days.
Compare amortized cost (Cost Explorer → "Amortized cost" view) with
unblended cost — if they diverge, the anomaly is in the unblended view
only and should be ignored.

## Credit consumption / expiration
A credit running out causes a step-function increase in net cost
without any underlying usage change. Check Billing Console → Credits
for any credit that expired in the anomaly window.

## Refund / reversal posting
AWS occasionally posts refunds or correction line items days after the
fact. A negative line item from last month being reversed appears as a
positive anomaly today. Filter Cost Explorer to "Refunds" charge type
to inspect.

## Linked account onboarding
A newly added member account in AWS Organizations can introduce
significant cost that looks like an anomaly at the management account
level but is expected at the organization level.

## Tag remediation surfacing
When a tagging gap is closed (e.g., previously untagged S3 buckets get
tagged), cost shifts from "untagged" to a specific team. Net cost is
unchanged at the org level but appears as a per-team anomaly.

## Currency / billing region change
Cross-region transfers between AWS billing entities (e.g., AISPL in
India) can create one-time line items. Rare but happens.
