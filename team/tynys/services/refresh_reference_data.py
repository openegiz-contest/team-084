"""Upgrade derived reference attributes without resetting scenarios or reports."""
from platform_client import NS, http
from setup_twins import sizing, csv_rows


def main():
    for twin, attribute, rows in [('energy', 'sizing', sizing()),
                                  ('substation', 'flex_stats', csv_rows('flex.csv'))]:
        if not rows:
            raise ValueError(f'No reference data for {attribute}')
        http('PUT', f'/api/2/things/{NS}:{twin}/attributes/{attribute}', rows)
        print(f'Updated {twin}.{attribute}: {len(rows)} rows')


if __name__ == '__main__':
    main()
