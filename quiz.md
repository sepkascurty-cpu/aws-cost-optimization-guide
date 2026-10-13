# Quiz: AWS Cost Optimization & FinOps 💸

5 scenarios. Answers are collapsed — no accidental cheating.

---

### Q1. The 7-year audit log

Your compliance team requires application logs retained for 7 years. They're accessed maybe twice a year during audits. Current setup: S3 Standard, 40 TB and growing. What do you change?

<details>
<summary>Answer</summary>

Move them to **S3 Glacier Deep Archive** ($0.00099/GB-mo vs $0.023 — roughly 23x cheaper) with a Lifecycle rule: Standard → Deep Archive after 30–90 days. Retrieval takes ~12 hours, which is fine for twice-a-year audits. Watch the 180-day minimum storage charge — don't lifecycle objects you'll delete sooner.
</details>

---

### Q2. Steady baseline, wrong commitment

A web API runs 24/7 on 50 `m7i.xlarge` instances across 3 AZs. The team bought 1-year **Reserved Instances** for all 50. Next quarter they migrate half the fleet to Graviton (`m7g.xlarge`) and move workers to Fargate. What did they get wrong?

<details>
<summary>Answer</summary>

**RI locks you to an instance family + region/AZ** — Graviton instances and Fargate aren't covered by those RIs, so half the commitment becomes stranded. **Compute Savings Plans** would have been the right call: they apply across EC2 instance families, Fargate, and Lambda, following the migration instead of fighting it.
</details>

---

### Q3. The nightly ETL

A data pipeline runs 4 hours every night (00:00–04:00), is fully idempotent, checkpoints to S3, and can tolerate a restart. Which purchase option, and why not the others?

<details>
<summary>Answer</summary>

**Spot Instances** — up to 90% off, and the workload is the textbook Spot fit: fault-tolerant, checkpointed, time-flexible. On-Demand wastes money on predictable batch; Savings Plans/RIs are for steady-state 24/7, not 4h/night; and the 2-minute interruption warning is harmless when you checkpoint to S3.
</details>

---

### Q4. The mystery spike

Cost Explorer shows EC2 spend +35% week-over-week, but instance count is unchanged and utilization is flat. Name two likely culprits and how you'd confirm each.

<details>
<summary>Answer</summary>

1. **Data transfer / NAT Gateway** — check Cost Explorer grouped by *Usage Type*; look for `NatGateway-Bytes` or `DataTransfer-Out`. NAT Gateway processing charges ($0.045/GB) ambush people constantly.
2. **New EBS volumes / snapshot sprawl or a larger instance type swapped in** — group by *Usage Type* for `EBS:VolumeUsage` growth, and check CloudTrail for `RunInstances`/`ModifyVolume` events. Bonus third: someone launched instances in a pricier region.
</details>

---

### Q5. The tag that pays

Finance asks: "How much did Project Phoenix cost last quarter?" Your accounts have zero cost allocation tags enabled. What's the minimum viable fix, and what prevents regression?

<details>
<summary>Answer</summary>

1. **Define the tag set** (`Project`, `Owner`, `Environment`, `CostCenter`), **activate them as cost allocation tags** in the Billing Console (tags are invisible in Cost Explorer until activated — allow ~24h).
2. Backfill via Tag Editor / Config rules.
3. **Prevent regression with an SCP** denying `ec2:RunInstances`, `rds:CreateDBInstance`, etc. when required tags are missing, plus a `finops_guard.py` anomaly scan in CI. No tags → no attribution → no accountability.
</details>

---

*Score: 5/5 — you're the person finance calls first. 3–4 — solid, tighten the weak spots. Below 3 — re-read the README's 30/60/90 plan. 🙂*
