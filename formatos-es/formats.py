# Spanish date formats for pretix's own formats (VivaWebs, 9 November 2026). pretix has none for «es», so its week
# calendar said «W 46, 2026 (09.11.–15.11.)» and the days «09/11/2026». Only these keys; the rest are Django's «es».
WEEK_FORMAT = r'\S\e\m\a\n\a \d\e\l j \d\e F'   # the previous / next week buttons: «Semana del 16 de noviembre»
WEEK_DAY_FORMAT = 'D j'                          # each day of the week calendar: «lun 9» (the month is in the week)
SHORT_MONTH_DAY_FORMAT = 'j M'                   # «9 nov»
