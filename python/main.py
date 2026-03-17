import asyncio
from funnel import fetch_candidates
from strategies.llm import filter_politics, tier1_screen, tier2_analyze

async def main():
    # Step 1: Market funnel
    candidates = fetch_candidates()
    if not candidates:
        print("No candidates found.")
        return

    # Step 2: AI filter — politics/world events only
    candidates = await filter_politics(candidates)
    print(f"After AI filter:    {len(candidates)} politics/world events markets")
    if not candidates:
        print("No politics/world events markets found.")
        return

    # Step 3: Tier 1 screen — pick top 5
    print(f"\nRunning Tier 1 screen on {len(candidates)} candidates...")
    picks = await tier1_screen(candidates)
    print(f"Tier 1 selected {len(picks)} markets for deep analysis")

    # Step 4: Tier 2 — analyze each pick in parallel
    print("\nRunning Tier 2 analysis...")
    results = await asyncio.gather(*[tier2_analyze(m) for m in picks])

    # Step 4: Print signals
    trades = [r for r in results if r is not None]
    print(f"\n{'='*60}")
    print(f"TRADE SIGNALS: {len(trades)} found")
    print(f"{'='*60}")
    for t in trades:
        print(f"\n  {t['direction']} {t['question'][:70]}")
        print(f"  Price: {t['price']:.2f}  Edge: {t['edge']:.2f}  Avg prob: {t['avg_prob']:.2f}")

if __name__ == "__main__":
    asyncio.run(main())
