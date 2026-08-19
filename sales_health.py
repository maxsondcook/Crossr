import sqlite3
from pathlib import Path
import matplotlib.pyplot as plt
import sales_history

DB_PATH = Path("sales_database.db")

ALL_SALES = [
    # Keeneland Sales
    "Keeneland January Horses Of All Ages Sale",
    "Keeneland April Two-Year-Olds In Training Sale",
    "Keeneland April Horses Of Racing Age Sale",
    "Keeneland April Selected Horses Of Racing Age Sale",
    "Keeneland July Selected Yearling Sale",
    "Keeneland September Yearling Sale",
    "Keeneland October Yearling Sale",
    "Keeneland November Breeding Stock Sale",
    "Keeneland November Horses Of Racing Age Sale",
    "Keeneland Breeding Stock Sale",
    "Keeneland The Championship Sale",

    # Fasig-Tipton Sales
    "Fasig Tipton Kentucky Winter Mixed",
    "Fasig Tipton Midlantic Winter Mixed",
    "Fasig Tipton Santa Anita Two-Year-Olds in Training",
    "Fasig Tipton Texas Two-Year-Olds In Training",
    "Fasig Tipton Midlantic May Two Year Olds In Training",
    "Fasig Tipton The Florida Sale",
    "Fasig Tipton The Gulfstream Sale",
    "Fasig Tipton The Calder Sale",
    "Fasig Tipton The July Sale",
    "Fasig Tipton July Selected Horses Of Racing Age",
    "Fasig Tipton Summer Selected Horses of Racing Age",
    "Fasig Tipton The Saratoga Sale",
    "Fasig Tipton Saratoga Selected Yearlings",
    "Fasig Tipton Saratoga Open Yearlings",
    "Fasig Tipton New York Bred Yearlings",
    "Fasig Tipton New York Bred Preferred Yearlings",
    "Fasig Tipton Texas Summer Yearlings",
    "Fasig Tipton Selected Yearlings Showcase",
    "Fasig Tipton Midlantic Fall Yearlings",
    "Fasig Tipton The Turf Showcase",
    "Fasig Tipton Saratoga Fall Mixed",
    "Fasig Tipton The Saratoga Fall Sale",
    "Fasig Tipton Kentucky October Yearlings",
    "Fasig Tipton The October Sale",
    "Fasig Tipton Texas Fall Mixed",
    "Fasig Tipton Texas Yearlings & Fall Mixed",
    "Fasig Tipton California Fall Yearlings",
    "Fasig Tipton The November Sale",
    "Fasig Tipton Texas December Mixed",
    "Fasig Tipton New York Horses Of Racing Age",
    "Fasig Tipton The Pin Oak Stud Sale"
]

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sale_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sale_title TEXT,
            sale_year INTEGER,
            hip TEXT,
            price_num REAL,
            is_rna INTEGER,
            is_out INTEGER
        )
    """)
    cursor.execute("DELETE FROM sale_records")
    conn.commit()
    conn.close()

def sync_csvs_to_sql():
    init_db()
    db_map = sales_history.scan_sales_files()
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    records_to_insert = []
    
    for year, sales in db_map.items():
        for title, filepath in sales.items():
            parsed_records = sales_history.load_and_process_csv(filepath)
            for r in parsed_records:
                records_to_insert.append((
                    title,
                    int(year),
                    str(r.get('hip', '')),
                    float(r.get('price_num', 0.0)),
                    1 if r.get('is_rna') else 0,
                    1 if r.get('is_out') else 0
                ))
                
    cursor.executemany("""
        INSERT INTO sale_records (sale_title, sale_year, hip, price_num, is_rna, is_out)
        VALUES (?, ?, ?, ?, ?, ?)
    """, records_to_insert)
    
    conn.commit()
    conn.close()

def get_sale_year_by_year_metrics(selected_sale_title):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT 
            sale_year,
            COUNT(CASE WHEN is_out = 0 THEN 1 END) as total_offered,
            SUM(CASE WHEN is_out = 0 AND is_rna = 0 AND price_num > 0 THEN price_num ELSE 0 END) as gross,
            AVG(CASE WHEN is_out = 0 AND is_rna = 0 AND price_num > 0 THEN price_num END) as avg_price,
            COUNT(CASE WHEN is_out = 0 AND is_rna = 0 AND price_num >= 1000000 THEN 1 END) as millionaires
        FROM sale_records
        WHERE LOWER(sale_title) LIKE ?
        GROUP BY sale_year
        ORDER BY sale_year ASC
    """, (f"%{selected_sale_title.lower()}%",))
    
    rows = cursor.fetchall()
    
    years, gross_list, totals_list, avgs_list, medians_list, millionaires_list = [], [], [], [], [], []

    for row in rows:
        year, total_offered, gross, avg_price, mil_count = row
        years.append(str(year))
        totals_list.append(total_offered)
        gross_list.append(gross or 0.0)
        avgs_list.append(avg_price or 0.0)
        millionaires_list.append(mil_count)

        cursor.execute("""
            SELECT price_num FROM sale_records
            WHERE LOWER(sale_title) LIKE ? AND sale_year = ? AND is_out = 0 AND is_rna = 0 AND price_num > 0
            ORDER BY price_num ASC
        """, (f"%{selected_sale_title.lower()}%", year))
        
        prices = [p[0] for p in cursor.fetchall()]
        n = len(prices)
        if n == 0:
            median = 0.0
        elif n % 2 == 1:
            median = prices[n // 2]
        else:
            median = (prices[(n // 2) - 1] + prices[n // 2]) / 2.0
            
        medians_list.append(median)

    conn.close()
    return years, gross_list, totals_list, avgs_list, medians_list, millionaires_list

def display_sales_health_dashboard():
    print("\n==================================")
    print("      SELECT A SALE TO ANALYZE    ")
    print("==================================")
    for idx, sale in enumerate(ALL_SALES, 1):
        print(f"[{idx:2d}] {sale}")
    print("----------------------------------")
    
    choice = input("\nSelect Sale Number (or 'X' to cancel): ").strip()
    if choice.upper() == 'X' or not choice.isdigit():
        return
        
    choice_idx = int(choice) - 1
    if choice_idx < 0 or choice_idx >= len(ALL_SALES):
        print("❌ Invalid selection.")
        return

    selected_sale = ALL_SALES[choice_idx]

    print(f"\n⏳ Syncing CSV dataset and running SQL queries for '{selected_sale}'...")
    sync_csvs_to_sql()
    
    years, gross, totals, avgs, medians, millionaires = get_sale_year_by_year_metrics(selected_sale)

    if not years:
        print(f"⚠️ No historical records found for '{selected_sale}'. Check CSV filenames in sales_data/.")
        return

    # Year-over-Year Summary Table
    print(f"\n📊 Year-over-Year Summary for: {selected_sale}")
    print(f"{'Year':<5} | {'Offered (YoY)':<16} | {'Gross (YoY)':<28} | {'Average (YoY)':<24} | {'Median (YoY)':<24} | {'$1M+ (YoY)'}")
    print("-" * 120)

    for i in range(len(years)):
        if i == 0:
            off_str = f"{totals[i]}"
            gross_str = f"${int(gross[i]):,}"
            avg_str = f"${int(avgs[i]):,}"
            med_str = f"${int(medians[i]):,}"
            mil_str = f"{millionaires[i]}"
        else:
            off_pct = ((totals[i] - totals[i-1]) / totals[i-1]) * 100 if totals[i-1] else 0
            gross_pct = ((gross[i] - gross[i-1]) / gross[i-1]) * 100 if gross[i-1] else 0
            avg_pct = ((avgs[i] - avgs[i-1]) / avgs[i-1]) * 100 if avgs[i-1] else 0
            med_pct = ((medians[i] - medians[i-1]) / medians[i-1]) * 100 if medians[i-1] else 0
            mil_pct = ((millionaires[i] - millionaires[i-1]) / millionaires[i-1]) * 100 if millionaires[i-1] else 0

            off_str = f"{totals[i]} ({off_pct:+.1f}%)"
            gross_str = f"${int(gross[i]):,} ({gross_pct:+.1f}%)"
            avg_str = f"${int(avgs[i]):,} ({avg_pct:+.1f}%)"
            med_str = f"${int(medians[i]):,} ({med_pct:+.1f}%)"
            mil_str = f"{millionaires[i]} ({mil_pct:+.1f}%)"

        print(f"{years[i]:<5} | {off_str:<16} | {gross_str:<28} | {avg_str:<24} | {med_str:<24} | {mil_str}")

    # Calculate Sale Highs
    max_totals = max(totals) if totals else 0
    max_gross = max(gross) if gross else 0
    max_avgs = max(avgs) if avgs else 0
    max_medians = max(medians) if medians else 0
    max_mil = max(millionaires) if millionaires else 0

    year_max_totals = years[totals.index(max_totals)] if max_totals in totals else "N/A"
    year_max_gross = years[gross.index(max_gross)] if max_gross in gross else "N/A"
    year_max_avgs = years[avgs.index(max_avgs)] if max_avgs in avgs else "N/A"
    year_max_medians = years[medians.index(max_medians)] if max_medians in medians else "N/A"
    year_max_mil = years[millionaires.index(max_mil)] if max_mil in millionaires else "N/A"

    # Sale Highs Table
    print(f"\n🏆 {selected_sale} Sales Highs")
    print("-" * 50)
    print(f"{'Most Horses Offered':<23} | {max_totals:,} in {year_max_totals}")
    print(f"{'Highest Gross':<23} | ${int(max_gross):,} in {year_max_gross}")
    print(f"{'Highest Average':<23} | ${int(max_avgs):,} in {year_max_avgs}")
    print(f"{'Highest Median':<23} | ${int(max_medians):,} in {year_max_medians}")
    print(f"{'Most Millionaires':<23} | {max_mil:,} in {year_max_mil}")

    # Convert 4-digit years to 2-digit years for graphs (e.g. "2010" -> "'10")
    years_2d = [f"'{y[-2:]}" for y in years]

    # Render clean 2x2 Grid Layout (Gross, Offered, Average, Median)
    plt.style.use('seaborn-v0_8-darkgrid' if 'seaborn-v0_8-darkgrid' in plt.style.available else 'default')
    fig, axes = plt.subplots(2, 2, figsize=(12, 8))
    fig.suptitle(f'SALES HEALTH TRENDS: {selected_sale.upper()}', fontsize=14, fontweight='bold')

    ax_gross = axes[0, 0]
    ax_totals = axes[0, 1]
    ax_avgs = axes[1, 0]
    ax_medians = axes[1, 1]

    all_axes = [ax_gross, ax_totals, ax_avgs, ax_medians]

    # Graph 1: Gross Sales ($ Millions)
    gross_m = [g / 1e6 for g in gross]
    ax_gross.plot(years_2d, gross_m, marker='o', color='#2b5c8f', linewidth=2)
    ax_gross.set_title('Gross Sales ($ Millions)', fontweight='bold')
    ax_gross.set_ylabel('USD ($M)')

    # Graph 2: Total Horses Offered
    ax_totals.bar(years_2d, totals, color='#4682b4', width=0.4)
    ax_totals.set_title('Total Horses Offered', fontweight='bold')
    ax_totals.set_ylabel('Head Count')

    # Graph 3: Average Price ($)
    ax_avgs.plot(years_2d, avgs, marker='s', color='#2e8b57', linewidth=2)
    ax_avgs.set_title('Average Price ($)', fontweight='bold')
    ax_avgs.set_ylabel('USD ($)')

    # Graph 4: Median Price ($)
    ax_medians.plot(years_2d, medians, marker='^', color='#d95f02', linewidth=2)
    ax_medians.set_title('Median Price ($)', fontweight='bold')
    ax_medians.set_ylabel('USD ($)')

    # Format year labels on all subplots
    for ax in all_axes:
        ax.set_xlabel('Year', fontweight='bold')
        ax.tick_params(labelbottom=True)

    plt.tight_layout(rect=[0, 0.03, 1, 0.95])
    plt.show()

if __name__ == "__main__":
    display_sales_health_dashboard()