# Experiment 0006: Dashboard UX Loop

## Question

Can an autonomous loop iteratively improve the dashboard's visual design and mobile responsiveness by evaluating screenshots against UX criteria?

## Why This Is an Experiment

The dashboard (dashboard.html, ~2000 lines) was built for desktop admin use. It has no mobile responsiveness — 8 tabs overflow, tables break, touch targets are undersized. The Karpathy Loop here modifies the HTML/CSS directly, screenshots the result at multiple viewports, and scores against a rubric.

## Known Issues (from visual audit)

1. **Navigation bar overflow**: 8 tabs + logo + buttons in one row, ~1200px of content
2. **No mobile breakpoints**: Only 2 media queries in 2000 lines
3. **Ask tab layout**: Input + button side-by-side breaks at narrow widths
4. **Tables**: 6-column data tables unreadable on mobile
5. **Touch targets**: Tab buttons and suggestion chips below 44px minimum
6. **Stat cards**: 4-column grid doesn't collapse

## Loop Design

```
FILE:    dashboard.html
METRIC:  Visual quality score (0-1) across 3 viewports
         Evaluated by vision LLM against rubric:
         - Layout integrity (no overflow, no hidden content)
         - Readability (text size, contrast, hierarchy)
         - Navigation usability (reachable, tappable, clear)
         - Information density (data visible, not wasted space)
         - Mobile-specific (touch targets, scrollability)

VIEWPORTS:
  - mobile:  375 × 812  (iPhone 14)
  - tablet:  768 × 1024 (iPad)
  - desktop: 1280 × 800

ITERATION:
  1. Analyze current scores and identify worst viewport/criterion
  2. Modify dashboard.html (CSS media queries, layout changes)
  3. Screenshot all 3 viewports
  4. Score each screenshot against rubric
  5. If improved: keep. If regressed on any viewport: revert.
```

## Evaluation Rubric

Each viewport is scored 0-1 on five criteria (equal weight):

| Criterion | 1.0 | 0.5 | 0.0 |
|-----------|-----|-----|-----|
| Layout integrity | No overflow, all content accessible | Minor overflow, scrollable | Content hidden or overlapping |
| Readability | Clear hierarchy, appropriate sizes | Readable but cramped | Text too small or truncated |
| Navigation | All tabs reachable, clear active state | Tabs accessible but awkward | Tabs hidden or unreachable |
| Info density | Good use of space, data visible | Some wasted space | Mostly empty or overwhelming |
| Mobile UX | Touch targets 44px+, native feel | Usable but desktop-ish | Unusable without zoom |

Overall = average across viewports × average across criteria.

## Success Criteria

- Mobile viewport score improves from baseline to >0.7
- No regression on desktop viewport
- Navigation works on all 3 viewports
