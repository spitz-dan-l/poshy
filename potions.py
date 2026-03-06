from collections import Counter
import csv
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from pprint import pprint
import re
from time import perf_counter
import tomllib


Potion = str
Ingredient = str

DATA_DIR = Path(__file__).with_name("data")
DEFAULT_INVENTORY_PATH = DATA_DIR / "inventory.toml"
DEFAULT_RECIPES_PATH = DATA_DIR / "recipes.toml"
DEFAULT_FOR_SALE_PATH = DATA_DIR / "for_sale.toml"
SUMMARY_PATH = Path(__file__).with_name("poshy_summary.md")
RECIPE_INGREDIENT_COLUMNS = ["Ingrediant 1", "Ingrediant 2", "Ingrediant 3", "Ingrediant 4"]
TOP_SECTION_LIMIT = 15
INGREDIENT_ALIASES = {
    "Citrine shard": "Citrine piece",
    "Dragonscale": "Dragon scale",
    "Green Herb": "Green herb",
    "Ibsidion shard": "Ibsidian shard",
    "Napa grass": "Nappa grass",
}


@dataclass
class Inventory:
    potions: Counter[Potion]
    ingredients: Counter[Ingredient]
    gold: int


@dataclass
class Recipe:
    target: Potion
    ingredients: Counter[Ingredient]


Prices = dict[Ingredient | Potion, int]
Recipes = list[Recipe]


@dataclass(frozen=True)
class RecipeBook:
    recipes: Recipes
    potion_prices: dict[Potion, int]


@dataclass
class BrewAction:
    pass


@dataclass
class UseIngredient(BrewAction):
    ingredient: Ingredient


@dataclass
class BuyIngredient(BrewAction):
    ingredient: Ingredient


@dataclass
class BuyPotion(BrewAction):
    potion: Potion


@dataclass
class Brew:
    potion: Potion
    actions: list[BrewAction]


@dataclass
class PotionAnalysis:
    recipe: Recipe
    direct_buy_price: int | None
    craft_copy_cost: int | None
    craft_copy_plan: tuple[Brew, ...]
    cheapest_copy_cost: int | None
    cheapest_copy_plan: tuple[Brew, ...]
    cheapest_copy_method: str | None
    max_copies: int
    max_copy_plan: tuple[Brew, ...]
    remaining_gold_after_max: int


@dataclass
class AnalysisReport:
    analyses: list[PotionAnalysis]
    duration_seconds: float


def load_toml(path: Path) -> dict:
    with path.open("rb") as handle:
        return tomllib.load(handle)


def normalize_ingredient_name(name: Ingredient) -> Ingredient:
    return INGREDIENT_ALIASES.get(name, name)


def normalize_ingredient_counts(raw_counts: dict[str, int]) -> Counter[Ingredient]:
    counts: Counter[Ingredient] = Counter()
    for name, count in raw_counts.items():
        counts[normalize_ingredient_name(name)] += int(count)
    return counts


def load_inventory(path: Path = DEFAULT_INVENTORY_PATH) -> Inventory:
    data = load_toml(path)
    gold = int(data["gold"])
    potions = Counter(data.get("potions", {}))
    ingredients = normalize_ingredient_counts(data.get("ingredients", {}))
    return Inventory(potions=potions, ingredients=ingredients, gold=gold)


def load_recipe_book(path: Path = DEFAULT_RECIPES_PATH) -> RecipeBook:
    data = load_toml(path)
    recipes: Recipes = []
    potion_prices: dict[Potion, int] = {}
    seen_targets: set[Potion] = set()

    for entry in data["recipes"]:
        target = entry["name"]
        if target in seen_targets:
            raise ValueError(f"Duplicate recipe target: {target}")
        seen_targets.add(target)
        ingredients = normalize_ingredient_counts(entry["ingredients"])
        recipes.append(Recipe(target=target, ingredients=ingredients))
        if "price" in entry:
            potion_prices[target] = int(entry["price"])

    return RecipeBook(recipes=recipes, potion_prices=potion_prices)


def load_for_sale(path: Path = DEFAULT_FOR_SALE_PATH) -> dict[Ingredient, int]:
    data = load_toml(path)
    prices: dict[Ingredient, int] = {}
    for name, price in data.get("ingredients", {}).items():
        ingredient = normalize_ingredient_name(name)
        value = int(price)
        existing = prices.get(ingredient)
        if existing is not None and existing != value:
            raise ValueError(f"Conflicting prices for ingredient: {ingredient}")
        prices[ingredient] = value
    return prices


def get_prices_v1(
    recipe_book: RecipeBook | None = None,
    for_sale: dict[Ingredient, int] | None = None,
) -> Prices:
    if recipe_book is None:
        recipe_book = load_recipe_book()
    if for_sale is None:
        for_sale = load_for_sale()
    return for_sale | recipe_book.potion_prices


def format_count_items(counter: Counter[str]) -> str:
    items = [(name, count) for name, count in sorted(counter.items()) if count > 0]
    if not items:
        return "none"
    return ", ".join(f"{name} x{count}" if count != 1 else name for name, count in items)


def describe_brew(brew: Brew) -> str:
    used = Counter()
    bought = Counter()
    bought_potion = False
    for action in brew.actions:
        if isinstance(action, UseIngredient):
            used[action.ingredient] += 1
        elif isinstance(action, BuyIngredient):
            bought[action.ingredient] += 1
        elif isinstance(action, BuyPotion):
            bought_potion = True

    if bought_potion:
        return f"Buy {brew.potion}"

    parts = [f"Make {brew.potion}"]
    details: list[str] = []
    if used:
        details.append(f"use {format_count_items(used)}")
    if bought:
        details.append(f"buy {format_count_items(bought)}")
    if details:
        parts.append(f"({'; '.join(details)})")
    return " ".join(parts)


def describe_plan(plan: tuple[Brew, ...]) -> str:
    if not plan:
        return "unavailable"
    return " -> ".join(describe_brew(step) for step in plan)


def simulate_craft_once(
    recipe: Recipe,
    ingredient_names: tuple[Ingredient, ...],
    counts: tuple[int, ...],
    gold: int,
    prices: Prices,
) -> None | tuple[Brew, tuple[int, ...], int]:
    remaining = list(counts)
    actions: list[BrewAction] = []
    new_gold = gold

    for index, ingredient in enumerate(ingredient_names):
        required = recipe.ingredients[ingredient]
        available = remaining[index]
        used = min(available, required)
        if used:
            remaining[index] -= used
            actions.extend(UseIngredient(ingredient) for _ in range(used))

        missing = required - used
        if missing:
            price = prices.get(ingredient)
            total_cost = 0 if price is None else price * missing
            if price is None or new_gold < total_cost:
                return None
            new_gold -= total_cost
            actions.extend(BuyIngredient(ingredient) for _ in range(missing))

    return Brew(recipe.target, actions), tuple(remaining), new_gold


def simulate_buy_once(
    recipe: Recipe,
    counts: tuple[int, ...],
    gold: int,
    prices: Prices,
) -> None | tuple[Brew, tuple[int, ...], int]:
    price = prices.get(recipe.target)
    if price is None or gold < price:
        return None
    return Brew(recipe.target, [BuyPotion(recipe.target)]), counts, gold - price


def analyze_recipe(recipe: Recipe, inventory: Inventory, prices: Prices) -> PotionAnalysis:
    ingredient_names = tuple(sorted(recipe.ingredients))
    start_counts = tuple(inventory.ingredients.get(name, 0) for name in ingredient_names)
    direct_buy_price = prices.get(recipe.target)

    craft_attempt = simulate_craft_once(recipe, ingredient_names, start_counts, inventory.gold, prices)
    buy_attempt = simulate_buy_once(recipe, start_counts, inventory.gold, prices)

    craft_copy_cost: int | None = None
    craft_copy_plan: tuple[Brew, ...] = ()
    if craft_attempt is not None:
        brew, _, new_gold = craft_attempt
        craft_copy_cost = inventory.gold - new_gold
        craft_copy_plan = (brew,)

    cheapest_copy_cost: int | None = None
    cheapest_copy_plan: tuple[Brew, ...] = ()
    cheapest_copy_method: str | None = None
    candidates: list[tuple[int, tuple[Brew, ...], str]] = []
    if craft_attempt is not None:
        candidates.append((inventory.gold - craft_attempt[2], (craft_attempt[0],), "craft"))
    if buy_attempt is not None:
        candidates.append((inventory.gold - buy_attempt[2], (buy_attempt[0],), "buy"))
    if candidates:
        cheapest_copy_cost, cheapest_copy_plan, cheapest_copy_method = min(
            candidates,
            key=lambda candidate: (candidate[0], len(candidate[1]), describe_plan(candidate[1])),
        )

    @lru_cache(maxsize=None)
    def solve(counts: tuple[int, ...], gold: int) -> tuple[int, int, tuple[Brew, ...]]:
        best_count = 0
        best_gold = gold
        best_plan: tuple[Brew, ...] = ()

        for attempt in (
            simulate_craft_once(recipe, ingredient_names, counts, gold, prices),
            simulate_buy_once(recipe, counts, gold, prices),
        ):
            if attempt is None:
                continue
            brew, new_counts, new_gold = attempt
            child_count, child_gold, child_plan = solve(new_counts, new_gold)
            candidate_count = 1 + child_count
            candidate_gold = child_gold
            candidate_plan = (brew,) + child_plan
            candidate_key = (-candidate_count, -candidate_gold, len(candidate_plan), describe_plan(candidate_plan))
            best_key = (-best_count, -best_gold, len(best_plan), describe_plan(best_plan))
            if candidate_key < best_key:
                best_count = candidate_count
                best_gold = candidate_gold
                best_plan = candidate_plan

        return best_count, best_gold, best_plan

    max_copies, remaining_gold_after_max, max_copy_plan = solve(start_counts, inventory.gold)
    return PotionAnalysis(
        recipe=recipe,
        direct_buy_price=direct_buy_price,
        craft_copy_cost=craft_copy_cost,
        craft_copy_plan=craft_copy_plan,
        cheapest_copy_cost=cheapest_copy_cost,
        cheapest_copy_plan=cheapest_copy_plan,
        cheapest_copy_method=cheapest_copy_method,
        max_copies=max_copies,
        max_copy_plan=max_copy_plan,
        remaining_gold_after_max=remaining_gold_after_max,
    )


def analyze_all_potions(inventory: Inventory, recipe_book: RecipeBook, for_sale: dict[Ingredient, int]) -> AnalysisReport:
    prices = get_prices_v1(recipe_book, for_sale)
    start = perf_counter()
    analyses = [analyze_recipe(recipe, inventory, prices) for recipe in recipe_book.recipes]
    duration_seconds = perf_counter() - start
    return AnalysisReport(analyses=analyses, duration_seconds=duration_seconds)


def write_summary(
    report: AnalysisReport,
    inventory: Inventory,
    recipe_book: RecipeBook,
    for_sale: dict[Ingredient, int],
    output_path: Path = SUMMARY_PATH,
) -> None:
    reachable = [analysis for analysis in report.analyses if analysis.max_copies > 0]
    unreachable = [analysis.recipe.target for analysis in report.analyses if analysis.max_copies == 0]
    savings_ranked = sorted(
        [
            analysis
            for analysis in reachable
            if analysis.direct_buy_price is not None
            and analysis.craft_copy_cost is not None
            and analysis.direct_buy_price > analysis.craft_copy_cost
        ],
        key=lambda analysis: (
            -(analysis.direct_buy_price - analysis.craft_copy_cost),
            analysis.craft_copy_cost,
            analysis.recipe.target,
        ),
    )
    max_ranked = sorted(
        reachable,
        key=lambda analysis: (
            -analysis.max_copies,
            analysis.cheapest_copy_cost if analysis.cheapest_copy_cost is not None else 10**9,
            analysis.recipe.target,
        ),
    )

    lines: list[str] = []
    lines.append("# Poshy Summary")
    lines.append("")
    lines.append("This report is an exact per-potion analysis.")
    lines.append("It does not enumerate every simultaneous multi-potion bundle, which is what made the old CSV output large and slow.")
    lines.append("")
    lines.append("## Inputs")
    lines.append(f"- Starting gold: {inventory.gold}")
    lines.append(f"- Nonzero inventory ingredients: {len([count for count in inventory.ingredients.values() if count > 0])}")
    lines.append(f"- Recipes loaded: {len(recipe_book.recipes)}")
    lines.append(f"- Shop items loaded: {len(for_sale)}")
    lines.append("")
    lines.append("## Analysis Stats")
    lines.append(f"- Reachable potions: {len(reachable)}")
    lines.append(f"- Unreachable potions: {len(unreachable)}")
    lines.append(f"- Runtime: {report.duration_seconds:.2f} seconds")
    lines.append("")
    lines.append("## Reachable Potions")
    lines.append("| Potion | Cheapest Copy | Method | Direct Buy | Craft Cost | Max Copies |")
    lines.append("| --- | ---: | --- | ---: | ---: | ---: |")
    for analysis in sorted(reachable, key=lambda analysis: analysis.recipe.target):
        direct_buy = "-" if analysis.direct_buy_price is None else str(analysis.direct_buy_price)
        craft_cost = "-" if analysis.craft_copy_cost is None else str(analysis.craft_copy_cost)
        cheapest = "-" if analysis.cheapest_copy_cost is None else str(analysis.cheapest_copy_cost)
        method = analysis.cheapest_copy_method or "-"
        lines.append(
            f"| {analysis.recipe.target} | {cheapest} | {method} | {direct_buy} | {craft_cost} | {analysis.max_copies} |"
        )
    lines.append("")

    lines.append(f"## Top {min(TOP_SECTION_LIMIT, len(savings_ranked))} Savings Opportunities")
    if savings_ranked:
        for index, analysis in enumerate(savings_ranked[:TOP_SECTION_LIMIT], start=1):
            savings = analysis.direct_buy_price - analysis.craft_copy_cost
            lines.append(
                f"{index}. {analysis.recipe.target}: buy {analysis.direct_buy_price}g vs craft {analysis.craft_copy_cost}g, save {savings}g"
            )
            lines.append(f"   - Cheapest craft: {describe_plan(analysis.craft_copy_plan)}")
    else:
        lines.append("No crafts are currently cheaper than direct buying.")
    lines.append("")

    lines.append(f"## Top {min(TOP_SECTION_LIMIT, len(max_ranked))} Max-Copy Potions")
    if max_ranked:
        for index, analysis in enumerate(max_ranked[:TOP_SECTION_LIMIT], start=1):
            cheapest = "-" if analysis.cheapest_copy_cost is None else f"{analysis.cheapest_copy_cost}g"
            lines.append(
                f"{index}. {analysis.recipe.target}: max {analysis.max_copies} copies, cheapest first copy {cheapest}, gold left after maxing {analysis.remaining_gold_after_max}g"
            )
            lines.append(f"   - Max-copy plan: {describe_plan(analysis.max_copy_plan)}")
    else:
        lines.append("No reachable potions.")
    lines.append("")

    if unreachable:
        lines.append("## Unreachable Potions")
        lines.append(", ".join(sorted(unreachable)))
        lines.append("")

    with output_path.open("w", encoding="utf-8") as handle:
        handle.write("\n".join(lines))


def parse_recipe_csv_v1(csv_path: str | Path) -> tuple[Recipes, dict[Potion, int]]:
    ingredient_regex = re.compile(r"^([\s\w]+) \((\d+)\)$")
    recipes: Recipes = []
    potion_prices: dict[Potion, int] = {}

    with Path(csv_path).open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            potion = (row.get("Potion") or "").strip()
            if not potion:
                continue
            try:
                price = int(row["Gold cost"])
            except (TypeError, ValueError):
                continue

            potion_prices[potion] = price
            raw_ingredients: dict[str, int] = {}
            for ingredient_col in RECIPE_INGREDIENT_COLUMNS:
                raw_value = (row.get(ingredient_col) or "").strip()
                if not raw_value:
                    continue
                match = ingredient_regex.fullmatch(raw_value)
                if match is None:
                    raise RuntimeError(f"Failed to parse ingredient '{raw_value}' for {potion}")
                ingredient = match.group(1)
                number = int(match.group(2))
                raw_ingredients[ingredient] = raw_ingredients.get(ingredient, 0) + number
            recipes.append(Recipe(potion, normalize_ingredient_counts(raw_ingredients)))

    return recipes, potion_prices


def demo() -> None:
    inventory = load_inventory()
    recipe_book = load_recipe_book()
    for_sale = load_for_sale()

    print("Initial inventory:")
    pprint(inventory.ingredients, width=160)
    print("Initial gold:", inventory.gold)
    print()

    report = analyze_all_potions(inventory, recipe_book, for_sale)
    write_summary(report, inventory, recipe_book, for_sale)
    print(f"Wrote summary to {SUMMARY_PATH}")


if __name__ == "__main__":
    demo()
