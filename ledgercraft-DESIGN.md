# LedgerCraft
Precise, tabular, accountant-approved -- numbers you can trust.

## Overview

LedgerCraft is a utility-first design system built for accounting software and invoice management platforms. It embraces the spreadsheet aesthetic with flat surfaces, crisp borders, and tight spacing optimized for dense tabular data. The palette is restrained and professional, using forest green for positive balances and amber for items requiring attention. Every pixel serves clarity, alignment, and numerical precision.

## Colors

- **Primary** (#15803D): Forest -- CTAs, positive balances, credits
- **Secondary** (#64748B): Steel -- secondary actions, column headers
- **Tertiary** (#B45309): Amber -- alerts, overdue notices, debits
- **Neutral** (#9CA3AF): Gray -- borders, disabled states, placeholders
- **Background** (#FAFAFA): App background, spreadsheet canvas
- **Surface** (#FFFFFF): Cards, table rows, form panels
- **Success** (#15803D): Credits, paid invoices, balanced
- **Warning** (#B45309): Overdue, pending review
- **Error** (#DC2626): Debits, errors, rejected entries
- **Info** (#2563EB): Informational notes, help links

## Typography

- **Headline Font**: Roboto Slab
- **Body Font**: Roboto
- **Mono Font**: IBM Plex Mono

- **Display**: Roboto Slab 30px bold, 1.2 line height, 0.01em tracking
- **Headline**: Roboto Slab 24px bold, 1.25 line height
- **Subhead**: Roboto 18px medium, 1.3 line height
- **Body Large**: Roboto 16px regular, 1.5 line height
- **Body**: Roboto 14px regular, 1.5 line height
- **Body Small**: Roboto 13px regular, 1.45 line height, 0.005em tracking
- **Caption**: Roboto 12px medium, 1.3 line height, 0.01em tracking
- **Overline**: Roboto 11px bold, 1.2 line height, 0.08em tracking
- **Code**: IBM Plex Mono 13px regular, 1.5 line height

## Spacing

- **Base unit:** 4px
- **Scale:** 4 / 8 / 12 / 16 / 20 / 24 / 32 / 40 / 48 / 64
- **Component padding:** 8px horizontal, 4px vertical (compact for table cells)
- **Section spacing:** 24px between sections, 8px between table-adjacent elements

## Border Radius

- **None** (0px): Table cells, table headers
- **Small** (2px): Buttons, inputs, chips
- **Medium** (4px): Cards, modals, dropdowns
- **Large** (6px): Feature panels, summary cards
- **XL** (8px): Dialog boxes, onboarding cards
- **Full** (9999px): Status dots, toggle switches

## Elevation

**Philosophy:** Flat design with borders as the primary depth indicator. Shadows are used sparingly -- only for overlays and dropdowns that must appear above the data grid. The spreadsheet aesthetic relies on borders, not elevation.
- **Subtle**: 1px offset, 2px blur, #0F172A at 4%
- **Medium**: 2px offset, 6px blur, #0F172A at 6%
- **Large**: 4px offset, 12px blur, #0F172A at 8%
- **Overlay**: 8px offset, 24px blur, #0F172A at 12%

## Components

### Buttons
#### Variants
- **Primary**: #15803D fill, #FFFFFF text, no border. Hover: #166534.
- **Secondary**: #F1F5F9 fill, #475569 text, 1px #CBD5E1 border. Hover: bg #E2E8F0.
- **Ghost**: transparent fill, #475569 text, no border. Hover: bg #F1F5F9, text #0F172A.
- **Destructive**: #DC2626 fill, #FFFFFF text, no border. Hover: #B91C1C.
#### Sizes
Sizes: Small (28px, 6px 12px, 12px, 2px), Medium (32px, 8px 16px, 13px, 2px), Large (40px, 10px 20px, 14px, 2px).
#### Disabled State
0.5 opacity.
- disabled cursor
- Border color fades to Subtle

### Cards
- **Background**: #FFFFFF default, #FFFFFF elevated.
- **Border**: 1px #E2E8F0 default, 1px #CBD5E1 elevated.
- **Radius**: 4px default, 4px elevated.
- **Padding**: 16px default, 20px elevated.
- **Shadow**: 2px offset, 6px blur, #0F172A at 6% elevated.
- **Hover**: border #CBD5E1 default, border #94A3B8 elevated.

### Inputs
#### Text Input
- **Default**: 1px #CBD5E1 border, #FFFFFF fill, #0F172A text, no shadow.
- **Hover**: 1px #94A3B8 border, #FFFFFF fill, #0F172A text, no shadow.
- **Focus**: 1px #15803D border, #FFFFFF fill, #0F172A text, 2px ring #15803D at 15% shadow.
- **Error**: 1px #DC2626 border, #FFFFFF fill, #0F172A text, 2px ring #DC2626 at 12% shadow.
- **Disabled**: 1px #E2E8F0 border, #FAFAFA fill, #94A3B8 text, no shadow.
** 32px **height, ** 6px 10px **padding, ** 2px **radius, ** 12px / 500 / #475569, 4px below **label, ** 11px / 400 / #94A3B8, 4px above **helper text.

### Chips
#### Filter Chip
** #F1F5F9 **background, ** #475569 / 12px / 500 **text, ** 1px #E2E8F0 **border, ** 2px **radius, ** 4px 8px **padding, ** bg #15803D1A, border #15803D, text #15803D **active.
#### Status Chip
** bg #15803D1A, text #15803D, border #15803D33 **paid, ** bg #B453091A, text #B45309, border #B4530933 **overdue, ** bg #64748B1A, text #64748B, border #64748B33 **draft.

### Lists
#### Default Item
** 36px **height, ** 6px 10px **padding, ** 1px #E2E8F0 **divider, ** bg #F1F5F9 **hover, ** bg #15803D0D, left 2px #15803D **selected, ** 13px / 400 / #0F172A **font.

### Checkboxes
** 16px **size, ** 1px #CBD5E1 **border, ** 2px **radius, ** bg #15803D, border #15803D, white checkmark **checked, ** bg #15803D, white dash **indeterminate, ** 50% opacity, disabled cursor **disabled, ** 13px / 400 / #0F172A, 8px gap **label.

### Radio Buttons
** 16px **size, ** 1px #CBD5E1 **border, ** border #15803D, inner dot #15803D (8px) **selected, ** 50% opacity, disabled cursor **disabled, ** 13px / 400 / #0F172A, 8px gap **label.

### Tooltips
** #0F172A **background, ** #F1F5F9 / 12px / 400 **text, ** 6px 10px **padding, ** 2px **radius, ** 220px **max width, ** 5px, same background **arrow, ** 250ms show, 0ms hide **delay.

## Do's and Don'ts

1. **Do** right-align all numerical columns (amounts, quantities, rates) for easy vertical scanning.
2. **Do** use consistent decimal places within each column -- two decimals for currency, four for tax rates.
3. **Do** use tabular (monospaced) numerals in all data tables so digits align column by column.
4. **Don't** mix debit/credit colors; green (#15803D) always means credit and red (#DC2626) always means debit.
5. **Do** use alternating row backgrounds (#FFFFFF / #F1F5F9) for tables with more than five rows.
6. **Don't** round totals for display; always show the exact calculated value with full precision.
7. **Do** provide sticky column headers and a frozen first column for wide data tables.
8. **Don't** use border-radius greater than 4px; the system relies on sharp, precise edges.
9. **Do** include column sort indicators and ensure all data tables are sortable by default.
10. **Don't** use decorative illustrations or playful iconography; the tone is strictly professional.