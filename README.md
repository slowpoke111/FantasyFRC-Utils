# FantasyFRC-Utils

## Config
1. Run `pip install -r requirements.txt` to install dependencies
2. Create a `.env` file and fill in your [TBA API key](https://www.thebluealliance.com/apidocs). Follow the template in `.env.example`.

---  

# Utilities
## `scoring.py`
Scores a draft using the TBA API.
1. Export draft to .csv in the same format as `/drafts/template.csv` and put in `/drafts/{event_code}.csv`
2. In `scoring.py` update the `EVENT_CODE` variable to the event you want to score (Should be the same as the filename without the suffix)
   2a. Optionally, configure scoring constants on lines 15-29
3. Run the script and the scored result will be placed in `/scores/`

## `autodraft.py`
1. Set event year and team list on lines 8 to 18
2. Run the script. A list of teams by OPR will be copied to your clipboard for the autodraft list. 
