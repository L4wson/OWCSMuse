// Payloads captured from the real service (`python -m owcsmuse serve`) and
// trimmed to a few rows each. Tests run against what the API actually sends, not
// against a shape invented alongside the component that consumes it.

export const PAYLOADS = {
  "versus": {
    "slug": "V5iNpKcbhata",
    "url": "/query/V5iNpKcbhata",
    "status": "ok",
    "question": "Sugarfree map record against Zeruhh",
    "sentence": {
      "text": "sug2rfree is 22-20 in maps against zeruhh across 2024-2026.",
      "spans": [
        {
          "start": 0,
          "end": 9,
          "kind": "player",
          "text": "sug2rfree",
          "entity_id": "58239fd5-cf2f-4894-a2ec-30fd026c262a"
        },
        {
          "start": 35,
          "end": 41,
          "kind": "player",
          "text": "zeruhh",
          "entity_id": "58faa695-b501-4642-a4d9-0e4c2ed8526d"
        }
      ]
    },
    "aggregate": {
      "description": "player vs player, map grain",
      "columns": [
        "subject",
        "opponent",
        "maps",
        "matches",
        "map_wins",
        "map_losses",
        "draws",
        "map_win_pct",
        "seasons",
        "first_map_at",
        "last_map_at"
      ],
      "rows": [
        {
          "subject": "sug2rfree",
          "opponent": "zeruhh",
          "maps": 42,
          "matches": 9,
          "map_wins": 22,
          "map_losses": 20,
          "draws": 0,
          "map_win_pct": 52.4,
          "seasons": [
            2024,
            2025,
            2026
          ],
          "first_map_at": "2024-03-21 21:54:58+00:00",
          "last_map_at": "2026-07-04 22:47:50+00:00"
        }
      ]
    },
    "evidence": {
      "available": true,
      "grain": "map",
      "description": "every map behind this record",
      "rows": [
        {
          "match_id": "1-1985af81-96d8-49ec-b71f-ec29739ea719",
          "round_number": 1,
          "played_at": "2026-07-04 22:47:50+00:00",
          "season": 2026,
          "championship_id": "32d9f289-5c3f-4ea9-b6b4-a62987c36d9a",
          "competition": "S9 NA OWCS Central - Playoffs",
          "team": "SpaceStation Gaming",
          "opponent": "Team Liquid",
          "map_name": "Ilios",
          "game_mode": "Control",
          "score": 2,
          "opponent_score": 1,
          "result": "won",
          "role": "Damage",
          "eliminations": 20,
          "deaths": 10,
          "assists": 2,
          "damage_dealt": 9730,
          "healing_done": 861,
          "damage_mitigated": 1339,
          "match_url": "https://www.faceit.com/en/ow2/room/1-1985af81-96d8-49ec-b71f-ec29739ea719"
        },
        {
          "match_id": "1-1985af81-96d8-49ec-b71f-ec29739ea719",
          "round_number": 2,
          "played_at": "2026-07-04 22:47:50+00:00",
          "season": 2026,
          "championship_id": "32d9f289-5c3f-4ea9-b6b4-a62987c36d9a",
          "competition": "S9 NA OWCS Central - Playoffs",
          "team": "SpaceStation Gaming",
          "opponent": "Team Liquid",
          "map_name": "Neon Junction",
          "game_mode": "Hybrid",
          "score": 3,
          "opponent_score": 4,
          "result": "lost",
          "role": "Damage",
          "eliminations": 32,
          "deaths": 13,
          "assists": 10,
          "damage_dealt": 16994,
          "healing_done": 2189,
          "damage_mitigated": 4211,
          "match_url": "https://www.faceit.com/en/ow2/room/1-1985af81-96d8-49ec-b71f-ec29739ea719"
        },
        {
          "match_id": "1-1985af81-96d8-49ec-b71f-ec29739ea719",
          "round_number": 3,
          "played_at": "2026-07-04 22:47:50+00:00",
          "season": 2026,
          "championship_id": "32d9f289-5c3f-4ea9-b6b4-a62987c36d9a",
          "competition": "S9 NA OWCS Central - Playoffs",
          "team": "SpaceStation Gaming",
          "opponent": "Team Liquid",
          "map_name": "Dorado",
          "game_mode": "Escort",
          "score": 2,
          "opponent_score": 1,
          "result": "won",
          "role": "Damage",
          "eliminations": 21,
          "deaths": 7,
          "assists": 12,
          "damage_dealt": 8420,
          "healing_done": 2410,
          "damage_mitigated": 2271,
          "match_url": "https://www.faceit.com/en/ow2/room/1-1985af81-96d8-49ec-b71f-ec29739ea719"
        }
      ],
      "page": 1,
      "page_size": 3,
      "total_rows": 42,
      "total_pages": 14,
      "has_more": true,
      "expanded_for": null,
      "expandable_by": null,
      "reason": null
    },
    "coverage": null,
    "limitations": [
      {
        "id": "main_series_2025_2026",
        "title": "The 2025 and 2026 main series is reconstructed from player history",
        "note": "The 2025 and 2026 part of this answer comes from the player-history crawl, not from FACEIT's championship endpoints, which do not publish those divisions."
      }
    ],
    "notes": [
      "A further 1 series between them in season 2026 (3 maps by series score) carry no map stats on FACEIT and are excluded from the record above."
    ],
    "entities": {
      "opponent": {
        "entity_type": "player",
        "entity_id": "58faa695-b501-4642-a4d9-0e4c2ed8526d",
        "current_name": "zeruhh",
        "matched_name": "zeruhh",
        "name_kind": "current_nickname",
        "score": 1.0,
        "matches": 48
      },
      "subject": {
        "entity_type": "player",
        "entity_id": "58239fd5-cf2f-4894-a2ec-30fd026c262a",
        "current_name": "sug2rfree",
        "matched_name": "sugarfree",
        "name_kind": "game_name",
        "score": 1.0,
        "matches": 53
      }
    },
    "candidates": {},
    "query": {
      "intent": "versus",
      "entity": "player",
      "metric": "map_win_rate",
      "filters": {
        "player": "sugarfree",
        "opponent": "zeruhh"
      },
      "aggregation": "total",
      "sort": "desc",
      "limit": 10,
      "min_maps": 1
    },
    "code": null,
    "reason": null,
    "suggestions": [],
    "parser": "rules"
  },
  "leaderboard": {
    "slug": "ShDMAo6IqI2h",
    "url": "/query/ShDMAo6IqI2h",
    "status": "ok",
    "question": "who had the most eliminations in 2024",
    "sentence": {
      "text": "kevsteer leads Eliminations with 1,109 across 49 maps in 2024, ahead of 9 others shown.",
      "spans": [
        {
          "start": 0,
          "end": 8,
          "kind": "player",
          "text": "kevsteer",
          "entity_id": "ef80a7e0-27ad-4c55-a2d7-52b687ba3b23"
        },
        {
          "start": 15,
          "end": 27,
          "kind": "stat",
          "text": "Eliminations",
          "entity_id": "Eliminations"
        }
      ]
    },
    "aggregate": {
      "description": "Eliminations leaderboard",
      "columns": [
        "player_id",
        "nickname",
        "maps_with_stat",
        "maps_played",
        "coverage_pct",
        "total",
        "avg_per_map",
        "seasons"
      ],
      "rows": [
        {
          "player_id": "ef80a7e0-27ad-4c55-a2d7-52b687ba3b23",
          "nickname": "kevsteer",
          "maps_with_stat": 49,
          "maps_played": 49,
          "coverage_pct": 100,
          "total": 1109,
          "avg_per_map": 22.632653061224488,
          "seasons": [
            2024
          ]
        },
        {
          "player_id": "b7a281ed-48ba-4f05-93d3-27ed9355c504",
          "nickname": "yung_kai",
          "maps_with_stat": 49,
          "maps_played": 49,
          "coverage_pct": 100,
          "total": 1102,
          "avg_per_map": 22.489795918367346,
          "seasons": [
            2024
          ]
        },
        {
          "player_id": "58239fd5-cf2f-4894-a2ec-30fd026c262a",
          "nickname": "sug2rfree",
          "maps_with_stat": 46,
          "maps_played": 46,
          "coverage_pct": 100,
          "total": 1015,
          "avg_per_map": 22.065217391304348,
          "seasons": [
            2024
          ]
        }
      ]
    },
    "evidence": {
      "available": true,
      "grain": "map",
      "description": "every map behind this number",
      "rows": [
        {
          "match_id": "1-9866418a-e962-49bf-889c-19c2054f6771",
          "round_number": 1,
          "played_at": "2024-04-28 20:12:58+00:00",
          "season": 2024,
          "championship_id": "32271a28-7b4c-465d-a928-9e84e9391495",
          "competition": "OWCS 2024: EMEA Stage 2 - Main Event",
          "team": "ENCE",
          "opponent": "SpaceStation Gaming",
          "map_name": "Busan",
          "game_mode": "Control",
          "score": 2,
          "opponent_score": 0,
          "result": "won",
          "role": "Damage",
          "eliminations": 24,
          "deaths": 3,
          "assists": 2,
          "damage_dealt": 9094,
          "healing_done": 647,
          "damage_mitigated": 586,
          "stat_value": 24,
          "stat_key": "Eliminations",
          "match_url": "https://www.faceit.com/en/ow2/room/1-9866418a-e962-49bf-889c-19c2054f6771"
        },
        {
          "match_id": "1-9866418a-e962-49bf-889c-19c2054f6771",
          "round_number": 2,
          "played_at": "2024-04-28 20:12:58+00:00",
          "season": 2024,
          "championship_id": "32271a28-7b4c-465d-a928-9e84e9391495",
          "competition": "OWCS 2024: EMEA Stage 2 - Main Event",
          "team": "ENCE",
          "opponent": "SpaceStation Gaming",
          "map_name": "Midtown",
          "game_mode": "Hybrid",
          "score": 1,
          "opponent_score": 3,
          "result": "lost",
          "role": "Damage",
          "eliminations": 15,
          "deaths": 10,
          "assists": 1,
          "damage_dealt": 13862,
          "healing_done": 35,
          "damage_mitigated": 608,
          "stat_value": 15,
          "stat_key": "Eliminations",
          "match_url": "https://www.faceit.com/en/ow2/room/1-9866418a-e962-49bf-889c-19c2054f6771"
        },
        {
          "match_id": "1-9866418a-e962-49bf-889c-19c2054f6771",
          "round_number": 3,
          "played_at": "2024-04-28 20:12:58+00:00",
          "season": 2024,
          "championship_id": "32271a28-7b4c-465d-a928-9e84e9391495",
          "competition": "OWCS 2024: EMEA Stage 2 - Main Event",
          "team": "ENCE",
          "opponent": "SpaceStation Gaming",
          "map_name": "Colosseo",
          "game_mode": "Push",
          "score": 1,
          "opponent_score": 0,
          "result": "won",
          "role": "Damage",
          "eliminations": 14,
          "deaths": 5,
          "assists": 10,
          "damage_dealt": 5723,
          "healing_done": 1463,
          "damage_mitigated": 3716,
          "stat_value": 14,
          "stat_key": "Eliminations",
          "match_url": "https://www.faceit.com/en/ow2/room/1-9866418a-e962-49bf-889c-19c2054f6771"
        }
      ],
      "page": 1,
      "page_size": 3,
      "total_rows": 49,
      "total_pages": 17,
      "has_more": true,
      "expanded_for": {
        "id": "ef80a7e0-27ad-4c55-a2d7-52b687ba3b23",
        "type": "player",
        "name": "kevsteer",
        "column": "player_id"
      },
      "expandable_by": "player_id",
      "reason": null
    },
    "coverage": {
      "stat_key": "Eliminations",
      "stat_kind": "countable",
      "maps_total": 4778,
      "maps_with_stat": 4778,
      "coverage_pct": 100,
      "seasons_with_stat": [
        2024
      ],
      "seasons_without_stat": null,
      "first_at": "2024-03-08 17:38:40+00:00",
      "last_at": "2024-04-28 23:32:48+00:00",
      "slice": "season 2024"
    },
    "limitations": [
      {
        "id": "offline_map_stats",
        "title": "Offline and LAN days have series results but no map stats",
        "note": "29 series in this slice in 2024 have no map stats on FACEIT, which is what offline and LAN days look like here. Those series carry a result but no maps, so they are absent from this map-grain answer."
      },
      {
        "id": "scope_na_emea",
        "title": "Scope is OWCS NA + EMEA main competition",
        "note": "Korea, China, Japan and the Pacific regions are not ingested, nor are open qualifiers, community cups or the relegation brackets held outside the main series. A leaderboard here is a leaderboard of NA and EMEA main-competition play, not of OWCS worldwide."
      }
    ],
    "notes": [],
    "entities": {},
    "candidates": {},
    "query": {
      "intent": "leaderboard",
      "entity": "player",
      "metric": "Eliminations",
      "filters": {
        "season": 2024
      },
      "aggregation": "total",
      "sort": "desc",
      "limit": 10,
      "min_maps": 1
    },
    "code": null,
    "reason": null,
    "suggestions": [],
    "parser": "rules"
  },
  "clarify": {
    "slug": "PXFay31aKx-G",
    "url": "/query/PXFay31aKx-G",
    "status": "clarify",
    "question": "tea record",
    "sentence": null,
    "aggregate": {
      "description": null,
      "columns": [],
      "rows": []
    },
    "evidence": null,
    "coverage": null,
    "limitations": [],
    "notes": [],
    "entities": {},
    "candidates": {
      "subject": [
        {
          "entity_type": "org",
          "entity_id": "team-peps",
          "current_name": "Team Peps",
          "matched_name": "Team Peps",
          "name_kind": "current_name",
          "score": 0.9,
          "matches": 55
        },
        {
          "entity_type": "team",
          "entity_id": "a58dedff-8045-46be-a13e-2402495b6a9d",
          "current_name": "Team Liquid",
          "matched_name": "Team Liquid",
          "name_kind": "current_name",
          "score": 0.9,
          "matches": 48
        },
        {
          "entity_type": "team",
          "entity_id": "d20d1868-8937-4a85-8706-bf936d265392",
          "current_name": "Team Z",
          "matched_name": "Team Z",
          "name_kind": "current_name",
          "score": 0.9,
          "matches": 20
        }
      ]
    },
    "query": {
      "intent": "team_record",
      "entity": "team",
      "metric": "record",
      "filters": {
        "subject": "tea"
      },
      "aggregation": "total",
      "sort": "desc",
      "limit": 10,
      "min_maps": 1
    },
    "code": "ambiguous_entity",
    "reason": "'tea' could be several player/teams; which one?",
    "suggestions": [
      "Re-ask with the exact name, or with the id shown in brackets."
    ],
    "parser": "rules"
  },
  "refusalWithEvidence": {
    "slug": "bgwoMdUT-1uE",
    "url": "/query/bgwoMdUT-1uE",
    "status": "cannot_answer",
    "question": "Team Falcons vs Crazy Raccoons",
    "sentence": {
      "text": "Team Falcons and Crazy Raccoons met, but none of those series has map stats on FACEIT.",
      "spans": [
        {
          "start": 17,
          "end": 31,
          "kind": "team",
          "text": "Crazy Raccoons",
          "entity_id": "4cbafe8a-486c-41f9-82e3-b7b84f1855d7"
        },
        {
          "start": 0,
          "end": 12,
          "kind": "team",
          "text": "Team Falcons",
          "entity_id": "2ab92d33-4c33-46e1-a13f-743a95291d0e"
        }
      ]
    },
    "aggregate": {
      "description": null,
      "columns": [],
      "rows": []
    },
    "evidence": {
      "available": true,
      "grain": "series",
      "description": "series they played whose maps FACEIT never recorded",
      "rows": [
        {
          "match_id": "1-c823aed8-9d75-44e0-a6b2-18bfa1a3e02b",
          "round_number": null,
          "played_at": "2024-06-02 23:59:13+00:00",
          "season": 2024,
          "championship_id": "33781289-61ea-43d5-ac79-1af825dcb291",
          "competition": "Dreamhack Dallas",
          "team": "Team Falcons",
          "opponent": "Crazy Raccoons",
          "best_of": 1,
          "score": 2,
          "opponent_score": 4,
          "result": "lost",
          "map_stats_recorded": false,
          "match_url": "https://www.faceit.com/en/ow2/room/1-c823aed8-9d75-44e0-a6b2-18bfa1a3e02b"
        },
        {
          "match_id": "1-cd3ccc44-1b18-463d-a4de-2d400ef020e9",
          "round_number": null,
          "played_at": "2024-06-02 19:30:37+00:00",
          "season": 2024,
          "championship_id": "33781289-61ea-43d5-ac79-1af825dcb291",
          "competition": "Dreamhack Dallas",
          "team": "Team Falcons",
          "opponent": "Crazy Raccoons",
          "best_of": 1,
          "score": 3,
          "opponent_score": 2,
          "result": "won",
          "map_stats_recorded": false,
          "match_url": "https://www.faceit.com/en/ow2/room/1-cd3ccc44-1b18-463d-a4de-2d400ef020e9"
        }
      ],
      "page": 1,
      "page_size": 3,
      "total_rows": 2,
      "total_pages": 1,
      "has_more": false,
      "expanded_for": null,
      "expandable_by": null,
      "reason": null
    },
    "coverage": null,
    "limitations": [
      {
        "id": "main_series_2025_2026",
        "title": "The 2025 and 2026 main series is reconstructed from player history",
        "note": "The 2025 and 2026 part of this answer comes from the player-history crawl, not from FACEIT's championship endpoints, which do not publish those divisions."
      }
    ],
    "notes": [
      "They did meet: 2 series in season 2024 (11 maps by series score), but FACEIT recorded no map stats for them, so none can count toward a map record."
    ],
    "entities": {
      "opponent": {
        "entity_type": "team",
        "entity_id": "4cbafe8a-486c-41f9-82e3-b7b84f1855d7",
        "current_name": "Crazy Raccoons",
        "matched_name": "Crazy Raccoons",
        "name_kind": "current_name",
        "score": 1.0,
        "matches": 5
      },
      "subject": {
        "entity_type": "team",
        "entity_id": "2ab92d33-4c33-46e1-a13f-743a95291d0e",
        "current_name": "Team Falcons",
        "matched_name": "Team Falcons",
        "name_kind": "current_name",
        "score": 0.8,
        "matches": 4
      }
    },
    "candidates": {},
    "query": {
      "intent": "versus",
      "entity": "team",
      "metric": "map_win_rate",
      "filters": {
        "team": "falcons",
        "opponent": "crazy raccoons"
      },
      "aggregation": "total",
      "sort": "desc",
      "limit": 10,
      "min_maps": 1
    },
    "code": "no_data",
    "reason": "Team Falcons and Crazy Raccoons met, but none of those series has map stats on FACEIT",
    "suggestions": [
      "The series results are known; only the per-map breakdown is missing."
    ],
    "parser": "rules"
  },
  "refusal": {
    "slug": "bRw9zEqYL64M",
    "url": "/query/bRw9zEqYL64M",
    "status": "cannot_answer",
    "question": "who has the best hero pool",
    "sentence": {
      "text": "hero picks are not in the FACEIT payloads.",
      "spans": []
    },
    "aggregate": {
      "description": null,
      "columns": [],
      "rows": []
    },
    "evidence": null,
    "coverage": null,
    "limitations": [],
    "notes": [],
    "entities": {},
    "candidates": {},
    "query": null,
    "code": "unsupported_metric",
    "reason": "hero picks are not in the FACEIT payloads",
    "suggestions": [
      "Ask `what stats are available` to see the tracked stat keys."
    ],
    "parser": "rules"
  },
  "suggestions": {
    "groups": [
      "Leaderboards",
      "Teams",
      "Head to head",
      "Players",
      "Across seasons",
      "Coverage",
      "Maps and modes"
    ],
    "suggestions": [
      {
        "question": "who had the most deaths in 2026",
        "group": "Leaderboards",
        "slug": "wyNCzeNmqMzS"
      },
      {
        "question": "who had the most healing done in 2026",
        "group": "Leaderboards",
        "slug": "n7_leBPZaKEg"
      },
      {
        "question": "who had the most damage mitigated in 2026",
        "group": "Leaderboards",
        "slug": "yDI9LPuk3de6"
      },
      {
        "question": "who had the most assists in 2026",
        "group": "Leaderboards",
        "slug": "ZNEImzg6R1RC"
      },
      {
        "question": "SpaceStation Gaming record",
        "group": "Teams",
        "slug": "yAt7cXRbIt1_"
      },
      {
        "question": "Twisted Minds record",
        "group": "Teams",
        "slug": "THQ4v32WVMcE"
      },
      {
        "question": "NTMR record",
        "group": "Teams",
        "slug": "jqEXT4So053D"
      },
      {
        "question": "Virtus pro record",
        "group": "Teams",
        "slug": "QEDjPofHxGku"
      }
    ]
  },
  "leaderboardPartial": {
    "slug": "iiyLDKg-gUEl",
    "url": "/query/iiyLDKg-gUEl",
    "status": "ok",
    "question": "who had the most final blows",
    "sentence": {
      "text": "sug2rfree leads Final Blows with 1,584 across 206 maps across 2025-2026, ahead of 9 others shown.",
      "spans": [
        {
          "start": 0,
          "end": 9,
          "kind": "player",
          "text": "sug2rfree",
          "entity_id": "58239fd5-cf2f-4894-a2ec-30fd026c262a"
        },
        {
          "start": 16,
          "end": 27,
          "kind": "stat",
          "text": "Final Blows",
          "entity_id": "Final Blows"
        }
      ]
    },
    "aggregate": {
      "description": "Final Blows leaderboard",
      "columns": [
        "player_id",
        "nickname",
        "maps_with_stat",
        "maps_played",
        "coverage_pct",
        "total",
        "avg_per_map",
        "seasons"
      ],
      "rows": [
        {
          "player_id": "58239fd5-cf2f-4894-a2ec-30fd026c262a",
          "nickname": "sug2rfree",
          "maps_with_stat": 160,
          "maps_played": 206,
          "coverage_pct": 77.7,
          "total": 1584,
          "avg_per_map": 9.9,
          "seasons": [
            2025,
            2026
          ]
        },
        {
          "player_id": "58faa695-b501-4642-a4d9-0e4c2ed8526d",
          "nickname": "zeruhh",
          "maps_with_stat": 156,
          "maps_played": 183,
          "coverage_pct": 85.2,
          "total": 1558,
          "avg_per_map": 9.987179487179487,
          "seasons": [
            2025,
            2026
          ]
        },
        {
          "player_id": "462c6480-274d-48a6-a5cf-d29d3b2dd786",
          "nickname": "LBBD7",
          "maps_with_stat": 163,
          "maps_played": 171,
          "coverage_pct": 95.3,
          "total": 1481,
          "avg_per_map": 9.085889570552148,
          "seasons": [
            2025,
            2026
          ]
        }
      ]
    },
    "evidence": {
      "available": true,
      "grain": "map",
      "description": "every map behind this number",
      "rows": [
        {
          "match_id": "1-0c28ddf5-09e3-4d63-88fc-55e0dc30dc13",
          "round_number": 1,
          "played_at": "2026-07-06 01:20:11+00:00",
          "season": 2026,
          "championship_id": "32d9f289-5c3f-4ea9-b6b4-a62987c36d9a",
          "competition": "S9 NA OWCS Central - Playoffs",
          "team": "SpaceStation Gaming",
          "opponent": "Dallas Fuel",
          "map_name": "Ilios",
          "game_mode": "Control",
          "score": 1,
          "opponent_score": 2,
          "result": "lost",
          "role": "Damage",
          "eliminations": 11,
          "deaths": 7,
          "assists": 1,
          "damage_dealt": 7324,
          "healing_done": 377,
          "damage_mitigated": 26,
          "stat_value": 4,
          "stat_key": "Final Blows",
          "match_url": "https://www.faceit.com/en/ow2/room/1-0c28ddf5-09e3-4d63-88fc-55e0dc30dc13"
        },
        {
          "match_id": "1-0c28ddf5-09e3-4d63-88fc-55e0dc30dc13",
          "round_number": 2,
          "played_at": "2026-07-06 01:20:11+00:00",
          "season": 2026,
          "championship_id": "32d9f289-5c3f-4ea9-b6b4-a62987c36d9a",
          "competition": "S9 NA OWCS Central - Playoffs",
          "team": "SpaceStation Gaming",
          "opponent": "Dallas Fuel",
          "map_name": "Neon Junction",
          "game_mode": "Hybrid",
          "score": 0,
          "opponent_score": 1,
          "result": "lost",
          "role": "Damage",
          "eliminations": 2,
          "deaths": 5,
          "assists": 0,
          "damage_dealt": 5241,
          "healing_done": 1001,
          "damage_mitigated": 1507,
          "stat_value": 0,
          "stat_key": "Final Blows",
          "match_url": "https://www.faceit.com/en/ow2/room/1-0c28ddf5-09e3-4d63-88fc-55e0dc30dc13"
        },
        {
          "match_id": "1-0c28ddf5-09e3-4d63-88fc-55e0dc30dc13",
          "round_number": 3,
          "played_at": "2026-07-06 01:20:11+00:00",
          "season": 2026,
          "championship_id": "32d9f289-5c3f-4ea9-b6b4-a62987c36d9a",
          "competition": "S9 NA OWCS Central - Playoffs",
          "team": "SpaceStation Gaming",
          "opponent": "Dallas Fuel",
          "map_name": "Dorado",
          "game_mode": "Escort",
          "score": 3,
          "opponent_score": 2,
          "result": "won",
          "role": "Damage",
          "eliminations": 23,
          "deaths": 7,
          "assists": 8,
          "damage_dealt": 9794,
          "healing_done": 2875,
          "damage_mitigated": 3668,
          "stat_value": 11,
          "stat_key": "Final Blows",
          "match_url": "https://www.faceit.com/en/ow2/room/1-0c28ddf5-09e3-4d63-88fc-55e0dc30dc13"
        }
      ],
      "page": 1,
      "page_size": 3,
      "total_rows": 206,
      "total_pages": 69,
      "has_more": true,
      "expanded_for": {
        "id": "58239fd5-cf2f-4894-a2ec-30fd026c262a",
        "type": "player",
        "name": "sug2rfree",
        "column": "player_id"
      },
      "expandable_by": "player_id",
      "reason": null
    },
    "coverage": {
      "stat_key": "Final Blows",
      "stat_kind": "countable",
      "maps_total": 14817,
      "maps_with_stat": 10030,
      "coverage_pct": 67.7,
      "seasons_with_stat": [
        2025,
        2026
      ],
      "seasons_without_stat": [
        2024
      ],
      "first_at": "2025-01-31 19:17:07+00:00",
      "last_at": "2026-07-06 01:20:11+00:00",
      "slice": ""
    },
    "limitations": [
      {
        "id": "offline_map_stats",
        "title": "Offline and LAN days have series results but no map stats",
        "note": "100 series in this slice in 2024, 2025, 2026 have no map stats on FACEIT, which is what offline and LAN days look like here. Those series carry a result but no maps, so they are absent from this map-grain answer."
      },
      {
        "id": "stats_2024",
        "title": "2024 carries 9 stat keys; 2025 and 2026 carry 47",
        "note": "'Final Blows' does not exist in 2024's 9-key stat set, so this covers 2025 and 2026 only even though no season filter says so."
      },
      {
        "id": "scope_na_emea",
        "title": "Scope is OWCS NA + EMEA main competition",
        "note": "Korea, China, Japan and the Pacific regions are not ingested, nor are open qualifiers, community cups or the relegation brackets held outside the main series. A leaderboard here is a leaderboard of NA and EMEA main-competition play, not of OWCS worldwide."
      },
      {
        "id": "main_series_2025_2026",
        "title": "The 2025 and 2026 main series is reconstructed from player history",
        "note": "The 2025 and 2026 part of this answer comes from the player-history crawl, not from FACEIT's championship endpoints, which do not publish those divisions."
      }
    ],
    "notes": [
      "'Final Blows' exists for 67.7% of maps in this slice; seasons without it: 2024; seasons with it: 2025, 2026. Rankings cover only the maps that have the stat."
    ],
    "entities": {},
    "candidates": {},
    "query": {
      "intent": "leaderboard",
      "entity": "player",
      "metric": "Final Blows",
      "filters": {},
      "aggregation": "total",
      "sort": "desc",
      "limit": 10,
      "min_maps": 1
    },
    "code": null,
    "reason": null,
    "suggestions": [],
    "parser": "rules"
  }
};

export const VERSUS = PAYLOADS.versus;
export const LEADERBOARD = PAYLOADS.leaderboard;
export const LEADERBOARD_PARTIAL = PAYLOADS.leaderboardPartial;
export const CLARIFY = PAYLOADS.clarify;
export const REFUSAL = PAYLOADS.refusal;
export const REFUSAL_WITH_EVIDENCE = PAYLOADS.refusalWithEvidence;
export const SUGGESTIONS = PAYLOADS.suggestions;

/** A fetch stand-in that answers from a route table and records what was asked. */
export function mockFetch(routes) {
  const calls = [];
  const fetchMock = async (url, options = {}) => {
    const path = String(url);
    const body = options.body ? JSON.parse(options.body) : null;
    calls.push({ url: path, method: options.method ?? "GET", body });
    for (const [pattern, responder] of routes) {
      if (pattern instanceof RegExp ? pattern.test(path) : path.includes(pattern)) {
        const result = typeof responder === "function" ? await responder({ path, body, calls }) : responder;
        if (result instanceof Error) throw result;
        const { status = 200, payload = null } = result ?? {};
        return { ok: status >= 200 && status < 300, status, json: async () => payload };
      }
    }
    return { ok: false, status: 404, json: async () => ({ detail: `no mock for ${path}` }) };
  };
  fetchMock.calls = calls;
  return fetchMock;
}

export const ok = (payload) => ({ status: 200, payload });
export const fail = (status, detail) => ({ status, payload: detail ? { detail } : null });

/** The same answer, paged: evidence rows change, the aggregate does not. */
export function pageOf(payload, page, rows = payload.evidence.rows) {
  const total = payload.evidence.total_rows;
  const size = payload.evidence.page_size;
  return {
    ...payload,
    evidence: {
      ...payload.evidence,
      page,
      rows,
      has_more: page * size < total,
      total_pages: Math.ceil(total / size),
    },
  };
}
