"""Explicit synthetic athlete choices entered through the real form, never defaults."""

def declare_entry_limits(page, minutes="480", longest="180"):
    for sport in ("вело", "бег", "плавание"):
        page.get_by_role("checkbox", name=f"Указать ограничения: {sport}", exact=True).check()
        page.get_by_label(f"{sport}: минут за 7 дней", exact=True).fill(minutes)
        page.get_by_label(f"{sport}: занятий за 7 дней", exact=True).fill("7" if minutes != "1" else "1")
        page.get_by_label(f"{sport}: максимум минут за занятие", exact=True).fill(longest)

