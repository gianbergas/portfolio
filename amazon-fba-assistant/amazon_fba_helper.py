import argparse
from dataclasses import dataclass


@dataclass
class UnitEconomics:
    sale_price: float
    product_cost: float
    inbound_shipping: float
    prep_and_packaging: float
    referral_fee_pct: float
    fba_fee: float
    other_costs: float
    acos_pct: float

    def to_dict(self) -> dict[str, float]:
        referral_fee = self.sale_price * (self.referral_fee_pct / 100)
        ad_cost = self.sale_price * (self.acos_pct / 100)
        total_cost_no_ads = (
            self.product_cost
            + self.inbound_shipping
            + self.prep_and_packaging
            + self.other_costs
            + referral_fee
            + self.fba_fee
        )
        profit_before_ads = self.sale_price - total_cost_no_ads
        profit_after_ads = profit_before_ads - ad_cost
        break_even_acos = (profit_before_ads / self.sale_price) * 100 if self.sale_price else 0.0
        margin_after_ads = (profit_after_ads / self.sale_price) * 100 if self.sale_price else 0.0

        return {
            "referral_fee": referral_fee,
            "ad_cost": ad_cost,
            "total_cost_no_ads": total_cost_no_ads,
            "profit_before_ads": profit_before_ads,
            "profit_after_ads": profit_after_ads,
            "break_even_acos": break_even_acos,
            "margin_after_ads": margin_after_ads,
        }


def round2(value: float) -> float:
    return round(value, 2)


def print_economics_report(e: UnitEconomics) -> None:
    data = e.to_dict()
    print("\n=== Report FBA ===")
    print(f"Prezzo vendita:            EUR {round2(e.sale_price)}")
    print(f"Costo prodotto:            EUR {round2(e.product_cost)}")
    print(f"Spedizione inbound:        EUR {round2(e.inbound_shipping)}")
    print(f"Prep/imballo:              EUR {round2(e.prep_and_packaging)}")
    print(f"Altri costi unitari:       EUR {round2(e.other_costs)}")
    print(f"Referral fee ({e.referral_fee_pct}%):      EUR {round2(data['referral_fee'])}")
    print(f"FBA fee:                   EUR {round2(e.fba_fee)}")
    print(f"Costo ads (ACOS {e.acos_pct}%):   EUR {round2(data['ad_cost'])}")
    print(f"Costo totale (no ads):     EUR {round2(data['total_cost_no_ads'])}")
    print(f"Utile prima ads:           EUR {round2(data['profit_before_ads'])}")
    print(f"Utile dopo ads:            EUR {round2(data['profit_after_ads'])}")
    print(f"Break-even ACOS:           {round2(data['break_even_acos'])}%")
    print(f"Margine netto dopo ads:    {round2(data['margin_after_ads'])}%")


def target_price_for_margin(
    target_margin_pct: float,
    target_acos_pct: float,
    product_cost: float,
    inbound_shipping: float,
    prep_and_packaging: float,
    other_costs: float,
    referral_fee_pct: float,
    fba_fee: float,
) -> float | None:
    fixed_costs = product_cost + inbound_shipping + prep_and_packaging + other_costs + fba_fee
    denominator = 1 - (target_margin_pct / 100) - (target_acos_pct / 100) - (referral_fee_pct / 100)
    if denominator <= 0:
        return None
    return fixed_costs / denominator


def inventory_plan(
    avg_daily_sales: float,
    lead_time_days: int,
    safety_days: int,
    current_stock: int,
    reorder_cycle_days: int = 30,
) -> dict[str, float]:
    reorder_point = avg_daily_sales * (lead_time_days + safety_days)
    suggested_order_qty = avg_daily_sales * (lead_time_days + safety_days + reorder_cycle_days)
    days_of_cover = (current_stock / avg_daily_sales) if avg_daily_sales > 0 else 0.0

    return {
        "reorder_point_units": reorder_point,
        "suggested_order_qty_units": suggested_order_qty,
        "days_of_cover": days_of_cover,
    }


def ask_float(prompt: str, default: float | None = None) -> float:
    while True:
        raw = input(f"{prompt}" + (f" [{default}]" if default is not None else "") + ": ").strip()
        if not raw and default is not None:
            return default
        try:
            return float(raw.replace(",", "."))
        except ValueError:
            print("Valore non valido, riprova.")


def ask_int(prompt: str, default: int | None = None) -> int:
    while True:
        raw = input(f"{prompt}" + (f" [{default}]" if default is not None else "") + ": ").strip()
        if not raw and default is not None:
            return default
        try:
            return int(raw)
        except ValueError:
            print("Valore non valido, riprova.")


def interactive_mode() -> None:
    while True:
        print("\n--- Amazon FBA Helper ---")
        print("1) Calcola margini unitari")
        print("2) Trova prezzo target (margine desiderato)")
        print("3) Pianifica riordino stock")
        print("0) Esci")
        choice = input("Scelta: ").strip()

        if choice == "0":
            print("Chiusura programma.")
            return
        if choice == "1":
            e = UnitEconomics(
                sale_price=ask_float("Prezzo vendita EUR"),
                product_cost=ask_float("Costo prodotto EUR"),
                inbound_shipping=ask_float("Spedizione inbound EUR", 0.0),
                prep_and_packaging=ask_float("Prep e imballo EUR", 0.0),
                referral_fee_pct=ask_float("Referral fee %", 15.0),
                fba_fee=ask_float("FBA fee EUR"),
                other_costs=ask_float("Altri costi unitari EUR", 0.0),
                acos_pct=ask_float("ACOS % atteso", 20.0),
            )
            print_economics_report(e)
        elif choice == "2":
            target_margin_pct = ask_float("Margine netto target %", 20.0)
            target_acos_pct = ask_float("ACOS target %", 15.0)
            product_cost = ask_float("Costo prodotto EUR")
            inbound_shipping = ask_float("Spedizione inbound EUR", 0.0)
            prep_and_packaging = ask_float("Prep e imballo EUR", 0.0)
            other_costs = ask_float("Altri costi unitari EUR", 0.0)
            referral_fee_pct = ask_float("Referral fee %", 15.0)
            fba_fee = ask_float("FBA fee EUR")

            target_price = target_price_for_margin(
                target_margin_pct=target_margin_pct,
                target_acos_pct=target_acos_pct,
                product_cost=product_cost,
                inbound_shipping=inbound_shipping,
                prep_and_packaging=prep_and_packaging,
                other_costs=other_costs,
                referral_fee_pct=referral_fee_pct,
                fba_fee=fba_fee,
            )
            if target_price is None:
                print("Non possibile: combinazione di margine/ACOS/referral troppo alta.")
            else:
                print(f"Prezzo target stimato: EUR {round2(target_price)}")
        elif choice == "3":
            avg_daily_sales = ask_float("Vendite medie giornaliere (unità)")
            lead_time_days = ask_int("Lead time fornitore (giorni)")
            safety_days = ask_int("Giorni di sicurezza", 10)
            current_stock = ask_int("Stock attuale (unità)")
            reorder_cycle_days = ask_int("Copertura ordine desiderata (giorni)", 30)

            plan = inventory_plan(
                avg_daily_sales=avg_daily_sales,
                lead_time_days=lead_time_days,
                safety_days=safety_days,
                current_stock=current_stock,
                reorder_cycle_days=reorder_cycle_days,
            )
            print("\n=== Piano stock ===")
            print(f"Reorder point:      {round2(plan['reorder_point_units'])} unità")
            print(f"Quantità suggerita: {round2(plan['suggested_order_qty_units'])} unità")
            print(f"Giorni copertura attuale: {round2(plan['days_of_cover'])}")
        else:
            print("Scelta non valida.")


def demo_mode() -> None:
    print("Demo rapida con dati esempio.\n")
    e = UnitEconomics(
        sale_price=29.99,
        product_cost=6.10,
        inbound_shipping=0.90,
        prep_and_packaging=0.40,
        referral_fee_pct=15.0,
        fba_fee=4.85,
        other_costs=0.55,
        acos_pct=18.0,
    )
    print_economics_report(e)

    target_price = target_price_for_margin(
        target_margin_pct=20.0,
        target_acos_pct=15.0,
        product_cost=6.10,
        inbound_shipping=0.90,
        prep_and_packaging=0.40,
        other_costs=0.55,
        referral_fee_pct=15.0,
        fba_fee=4.85,
    )
    print(f"\nPrezzo target per margine 20% con ACOS 15%: EUR {round2(target_price or 0.0)}")

    plan = inventory_plan(
        avg_daily_sales=12,
        lead_time_days=35,
        safety_days=10,
        current_stock=450,
        reorder_cycle_days=30,
    )
    print("Riordino esempio:")
    print(f"- Reorder point: {round2(plan['reorder_point_units'])} unità")
    print(f"- Ordine suggerito: {round2(plan['suggested_order_qty_units'])} unità")
    print(f"- Copertura stock attuale: {round2(plan['days_of_cover'])} giorni")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Programma esempio per supportare attività Amazon FBA."
    )
    parser.add_argument(
        "--mode",
        choices=["interactive", "demo"],
        default="interactive",
        help="interactive = menu completo, demo = esempio automatico",
    )
    args = parser.parse_args()

    if args.mode == "demo":
        demo_mode()
    else:
        interactive_mode()


if __name__ == "__main__":
    main()
