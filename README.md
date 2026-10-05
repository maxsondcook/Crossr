"""
This is a project that outputs horse pedigrees as searched by horse name or the major American stud farms in 
Kentucky (Airdrie Stud, Claiborne Farm, Coolmore Ashford Stud, Darley Stud, Gainesway Farm, Hill 'n' Dale, Lane's End Farm, 
Spendthrift Farm, Taylor Made Farm, Three Chimneys Farm, and WinStar Farm). It also allows the user to input pedigrees. 
For example, if they have a new foal or if their horse is not already in the pedigrees_database.py file. 
Additionally, it allows the user to see stallion stats (rankings, broodmare sire rankings, best value sires, and searches by crop status) 
as well as featuring a hypomating engine.

The hypomating engine works by asking the user to input a broodmare. If the broodmare is not in the pedigrees database, it will ask the 
user to input the pedigree. After inputting the pedigree, the user will be asked if they have a preferred surface or a price range. The 
engine will then search through a file of all Graded Stakes Winners and suggest stallions to the user based on past crosses. However, if 
the broodmare has already produced a GSW (Graded Stakes Winner), the engine will recognize that through the graded stakes winner 
spreadsheet and output that specific stallion.

For example, the broodmare Virginia Key produced the 2025 G1 Florida Derby winner, Tappan Street. Tappan Street is by Into Mischief and 
Virginia Key is by Distorted Humor. Because the Florida Derby is a dirt race, the code marks this down as a successful cross between 
Into Mischief x Distorted Humor for dirt. If the user selects turf, this cross won't be suggested (unless it is also a proven turf cross). 
The next factor is price. If you don't have $250,000 but you do have $50,000, the code provides ancestors and sons of Into Mischief 
(such as Barnes, Authentic, Audible, etc.). This function includes an inbreeding failsafe. For example, Citizen Bull would not be suggested 
because he is already bred on that exact same Into Mischief x Distorted Humor mare cross.

The final aspect of my project is a sales engine that contains all available sales data from Fasig-Tipton (2004-) and Keeneland (1999-) 
sales. The user can search by sale to find key sales stats, with the ability to sort by price, filter by sex, etc. The second option within 
the sales engine is a search by stallion, which returns a list of all horses by that sire that entered an auction (which can also be sorted 
and filtered), along with major sales stats for the entirety of their stud career and their specific sales stats for the last 5 years. 
Lastly, users can type in a horse's name, foaling year, sire, and dam in order to see that individual horse's sales history.

There are also numerous other files that are meant to keep the main file working properly.

Crossr website (v1)
-------------------
The public UI never serves `sales_data/` or `graded_stakes_winners.csv`. Those stay on the API server; the browser only receives JSON.

1. Index sales once: `python3 scripts/index_sales.py`
2. API: `uvicorn crossr_api.app:app --reload --port 8000`
3. UI: `cd web && npm install && npm run dev` then open http://localhost:3000

Docker: `docker compose up --build` after the sales index exists.

Do not upload Keeneland/Fasig-Tipton CSVs to a public frontend host (Vercel). Keep them on the API machine only.
"""
