import calendar
import time
import pandas as pd

thisYear = int(time.strftime("%Y"))
thisMonth = int(time.strftime("%m"))


def generateCalendar(thisYear, thisMonth):
    prevYear = thisYear
    nextYear = thisYear
    prevMonth = thisMonth - 1
    nextMonth = thisMonth + 1
    if prevMonth == 0:
        prevMonth = 12
        prevYear = thisYear - 1
        nextYear = thisYear + 1
    cal = calendar.Calendar(firstweekday = 0)
    currentMonthDays = list(cal.itermonthdays(thisYear, thisMonth))
    prevMonthDays = list(cal.itermonthdays(prevYear, prevMonth))
    nextMonthDays = list(cal.itermonthdays(nextYear, nextMonth))
    
    fullCalendar = []
    
    missingDaysFromPrev = sum(day == 0 for day in currentMonthDays[:7])
    fullCalendar.extend(day for day in prevMonthDays[-missingDaysFromPrev:] if day != 0)
    fullCalendar.extend(day for day in currentMonthDays if day != 0)
    
    missingDaysFromNext = (7 - len(fullCalendar) % 7) % 7
    if missingDaysFromNext < 7:
        fullCalendar.extend(nextMonthDays[:missingDaysFromNext])
        
    df = pd.DataFrame({'Day': fullCalendar})
    df['Year'] = thisYear
    df['Month'] = thisMonth
    df.loc[:missingDaysFromPrev - 1, 'Month'] = prevMonth
    df.loc[len(fullCalendar) - missingDaysFromNext:, 'Month'] = nextMonth  
    if nextMonth == 13:
    	nextMonth = 1
    
    return df



    
calendar = generateCalendar(thisYear, thisMonth)
print(f"{calendar}")
#print(f"{nextMonth}")
