# Algorithm Logging Guide

The MQTT Interceptor includes optional algorithm logging to help you analyze and tune the charging algorithm performance.

## What Gets Logged

The algorithm logger captures all the key inputs and outputs of the charging algorithm in a single CSV row:

- `timestamp` - When the calculation occurred
- `house_battery_soc` - House battery state of charge (%)
- `ev_battery_soc` - EV battery state of charge (%)
- `original_load` - Original load value from Solar Assistant (W)
- `modified_load` - Modified load value sent to EVSE (W)
- `load_difference` - Difference between modified and original load (W)
- `battery_priority_score` - Calculated priority score (house_soc + (80 - ev_soc))
- `charging_priority` - Algorithm decision (EV_PRIORITY, HOUSE_PRIORITY, or BALANCED)

## Configuration

Enable algorithm logging in `config/config.yaml`:

```yaml
algorithm_logging:
  # Enable logging
  enabled: true
  
  # Log every 10th calculation (reduces file size)
  log_every_n_calculations: 10
  
  # Where to store log files
  log_directory: "data/algorithm_logs"
  
  # Delete files older than 30 days
  max_age_days: 30
```

## File Management

### Daily Log Files
- New CSV file created each day: `algorithm_log_2024-01-15.csv`
- Files automatically include CSV headers
- Old files automatically deleted after `max_age_days`

### Log Frequency Control
The `log_every_n_calculations` setting prevents massive log files:
- If your EVSE gets 1000 load updates per day
- Setting `log_every_n_calculations: 10` results in ~100 log entries per day
- This gives you representative data without overwhelming file sizes

## Analysis in Excel

1. **Open the CSV file** in Excel or Google Sheets
2. **Create charts** comparing inputs vs outputs:
   - Battery levels over time
   - Load modifications over time
   - Priority decisions over time

### Useful Excel Charts

**Battery Comparison Chart:**
- X-axis: timestamp
- Y-axis: house_battery_soc and ev_battery_soc
- Chart type: Line chart with two series

**Load Modification Chart:**
- X-axis: timestamp  
- Y-axis: original_load and modified_load
- Chart type: Line chart with two series

**Load Impact Chart:**
- X-axis: timestamp
- Y-axis: load_difference
- Chart type: Column chart (positive = more charging, negative = less charging)

**Priority Distribution:**
- Create a pivot table with charging_priority as rows
- Count occurrences to see EV_PRIORITY vs HOUSE_PRIORITY vs BALANCED

## Tuning Based on Analysis

### Common Patterns to Look For

**1. EV Battery Always Low**
- Many EV_PRIORITY decisions but EV battery stays low
- **Solution**: Lower `ev_priority_threshold` or increase `charge_modifier_multiplier`

**2. House Battery Always Low**  
- Many HOUSE_PRIORITY decisions but house battery stays low
- **Solution**: Lower `house_priority_threshold`

**3. Too Conservative**
- Mostly BALANCED decisions, small load_difference values
- **Solution**: Increase `charge_modifier_multiplier`

**4. Too Aggressive**
- Very large load_difference swings
- **Solution**: Decrease `charge_modifier_multiplier`

### Example Analysis

If your log shows:
```csv
timestamp,house_battery_soc,ev_battery_soc,original_load,modified_load,load_difference,battery_priority_score,charging_priority
2024-01-15T10:00:00,-2000,85,20,-1500,500,105,EV_PRIORITY
2024-01-15T10:05:00,-1800,85,25,-1200,600,105,EV_PRIORITY
```

This shows:
- House battery high (85%), EV battery low (20%)
- Algorithm correctly choosing EV_PRIORITY
- Load being modified to send more power to EV (+500-600W)
- Battery priority score of 105 triggering EV priority

## File Locations

### Docker Deployment
- Log files: `./data/algorithm_logs/algorithm_log_YYYY-MM-DD.csv`
- Access via: `docker exec -it mqtt-interceptor ls /app/data/algorithm_logs/`

### Direct Installation
- Log files: `data/algorithm_logs/algorithm_log_YYYY-MM-DD.csv`
- View with: `ls data/algorithm_logs/`

## Troubleshooting

### No Log Files Created
1. Check `algorithm_logging.enabled: true` in config
2. Verify the service is receiving load messages
3. Check log directory permissions
4. Look for errors in service logs

### Log Files Too Large
- Increase `log_every_n_calculations` (e.g., from 10 to 50)
- Decrease `max_age_days` for faster cleanup

### Log Files Too Small
- Decrease `log_every_n_calculations` (e.g., from 10 to 5)
- Check that load modifications are happening frequently enough

## Best Practices

1. **Start with logging disabled** for initial deployment
2. **Enable logging for 1-2 weeks** when you want to tune the algorithm
3. **Analyze weekly** to identify patterns
4. **Make incremental changes** to one parameter at a time
5. **Disable logging** once you're happy with performance to save disk space

This simple logging approach gives you exactly what you need to understand and optimize your charging algorithm without the complexity of databases or heavy analysis tools.
