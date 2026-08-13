/**
 * Fixtures captured verbatim from the running backend, so component tests
 * assert against the real response shape - including `graph_reasoning` - rather
 * than a hand-written guess that can drift from the API.
 *
 * Traversals are filtered to the exercises retained in this slice so the fixture
 * stays internally consistent.
 */
import type {
  CopilotResponse,
  GenerateWorkoutResponse,
  MemberHistory,
  MemberSummary,
} from '@/lib/types';

const raw = {
  "member": {
    "id": "mbr_01HX9JORDAN",
    "name": "Jordan Rivera",
    "tier": "1:1 Coaching",
    "age": 41,
    "primary_goal": "Build lower-body strength",
    "goals": [
      {
        "id": "goal_strength",
        "text": "Build lower-body strength",
        "priority": 1,
        "target_date": "2026-09-01"
      },
      {
        "id": "goal_knee",
        "text": "Return to pain-free squatting after left-knee flare-up",
        "priority": 1,
        "target_date": "2026-07-15"
      },
      {
        "id": "goal_sleep",
        "text": "Average 7+ hours of sleep on weeknights",
        "priority": 2,
        "target_date": null
      }
    ],
    "active_injuries": [
      {
        "id": "inj_knee_left",
        "region": "left knee",
        "joint": "knee",
        "status": "recovering",
        "severity": "mild",
        "since": "2026-05-10",
        "notes": "Patellofemoral pain after a hiking trip. Cleared for low-impact loading; avoid deep knee flexion under load and plyometrics.",
        "snomedct_hint": "Look up patellofemoral pain syndrome / knee joint structures in SNOMED CT via NCI EVS."
      }
    ],
    "equipment_available": [
      "Dumbbell",
      "Kettlebell",
      "Yoga Mat",
      "Resistance Band - Loop",
      "Flat Bench"
    ],
    "latest_adherence_pct": 50.0,
    "adherence_trend": "declining",
    "churn_risk_level": "elevated",
    "churn_risk_reasons": [
      "Weekly adherence fell from 100% to 50% over 2 weeks",
      "One skipped session with a fatigue/work explanation",
      "Login frequency down vs. prior month"
    ],
    "avg_sleep_hours": 6.27,
    "preferred_session_minutes": 50,
    "morning_tasks": [
      {
        "type": "celebrate",
        "text": "Congratulate Jordan on completing yesterday's lower-body session — first pain-free squat work since the knee flare-up."
      },
      {
        "type": "review_risk",
        "text": "Check churn risk: adherence dropped 100% → 50% over the last two weeks."
      }
    ],
    "brief_date": "2026-06-04"
  },
  "history": {
    "member_id": "mbr_01HX9JORDAN",
    "sessions": [
      {
        "date": "2026-06-03",
        "title": "Lower Body - Bands & DB",
        "completed": true,
        "planned": true,
        "duration_min": 28,
        "rpe": 6,
        "exercises": [
          "Goblet Squat (box-supported)",
          "Hip Thrust",
          "Banded Lateral Walk"
        ]
      },
      {
        "date": "2026-06-01",
        "title": "Upper Body Push",
        "completed": true,
        "planned": true,
        "duration_min": 31,
        "rpe": 7,
        "exercises": [
          "DB Floor Press",
          "Half-Kneeling DB Press",
          "Band Pull-Apart"
        ]
      },
      {
        "date": "2026-05-29",
        "title": "Full Body",
        "completed": false,
        "planned": true,
        "duration_min": 0,
        "rpe": null,
        "exercises": []
      },
      {
        "date": "2026-05-27",
        "title": "Lower Body",
        "completed": true,
        "planned": true,
        "duration_min": 26,
        "rpe": 6,
        "exercises": [
          "Step-Up",
          "KB Romanian Deadlift",
          "Wall Sit"
        ]
      }
    ],
    "chat": [
      {
        "ts": "2026-06-03T18:42:00-07:00",
        "from": "member",
        "text": "Knocked out the lower body session! Knee felt okay with the box squats.",
        "attachments": []
      },
      {
        "ts": "2026-06-03T19:05:00-07:00",
        "from": "coach",
        "text": "Love it — that's the green light we wanted. How's the knee this morning vs. after?",
        "attachments": []
      },
      {
        "ts": "2026-05-30T08:12:00-07:00",
        "from": "member",
        "text": "Skipped Thursday, work blew up and I was wiped. Sorry!",
        "attachments": []
      },
      {
        "ts": "2026-05-22T07:50:00-07:00",
        "from": "member",
        "text": "Still no barbell at home btw — only DBs and a kettlebell.",
        "attachments": [
          {
            "type": "image",
            "caption": "Home setup photo (synthetic placeholder)"
          }
        ]
      }
    ],
    "adherence": [
      {
        "week_of": "2026-05-12",
        "pct": 100.0
      },
      {
        "week_of": "2026-05-19",
        "pct": 100.0
      },
      {
        "week_of": "2026-05-26",
        "pct": 75.0
      },
      {
        "week_of": "2026-06-02",
        "pct": 50.0
      }
    ],
    "sleep": [
      {
        "label": "Night 1",
        "hours": 6.1
      },
      {
        "label": "Night 2",
        "hours": 5.4
      },
      {
        "label": "Night 3",
        "hours": 7.2
      },
      {
        "label": "Night 4",
        "hours": 6.0
      },
      {
        "label": "Night 5",
        "hours": 5.1
      },
      {
        "label": "Night 6",
        "hours": 7.8
      },
      {
        "label": "Night 7",
        "hours": 6.3
      }
    ]
  },
  "workout": {
    "request_id": "19eadb5dd0e7",
    "workout": {
      "title": "45-Minute Lower Body Session",
      "duration_minutes": 45,
      "sections": [
        {
          "name": "warmup",
          "exercises": [
            {
              "exercise_id": "1423ff58-68de-47da-8884-cb6f438f5774",
              "name": "Walking Toe Touches",
              "sets": 1,
              "reps": "8-10",
              "duration_seconds": null,
              "rest_seconds": 20,
              "rationale": "Selected from the graph-approved candidate pool (matches requested focus (muscles), supports goal: \"Build lower-body strength\").",
              "coaching_note": null,
              "substituted_for": null
            },
            {
              "exercise_id": "0a4d99cf-5075-468e-9551-b9f8efa267f1",
              "name": "World's Greatest Stretch",
              "sets": 1,
              "reps": "8-10",
              "duration_seconds": null,
              "rest_seconds": 20,
              "rationale": "Selected from the graph-approved candidate pool (safety adjustment -8, matches requested focus (muscles)).",
              "coaching_note": "Keep range of motion pain-free; stop short of deep knee flexion.",
              "substituted_for": null
            }
          ]
        },
        {
          "name": "main",
          "exercises": [
            {
              "exercise_id": "0a2dc786-fb42-4571-9b26-f58cdeb2c70e",
              "name": "Bodyweight Pike",
              "sets": 3,
              "reps": "8-12",
              "duration_seconds": null,
              "rest_seconds": 75,
              "rationale": "Selected from the graph-approved candidate pool (matches requested focus (muscles)).",
              "coaching_note": null,
              "substituted_for": null
            },
            {
              "exercise_id": "01f5a2bb-ecf7-4168-92b3-35bd78592e26",
              "name": "High Plank Bird Dog",
              "sets": 3,
              "reps": "8-12",
              "duration_seconds": null,
              "rest_seconds": 75,
              "rationale": "Selected from the graph-approved candidate pool (safety adjustment -8, matches requested focus (joints)).",
              "coaching_note": "Keep range of motion pain-free; stop short of deep knee flexion.",
              "substituted_for": null
            },
            {
              "exercise_id": "02d6478f-0579-480b-a188-8e719d4fda14",
              "name": "Low Copenhagen Plank",
              "sets": 3,
              "reps": null,
              "duration_seconds": 40,
              "rest_seconds": 75,
              "rationale": "Selected from the graph-approved candidate pool (safety adjustment -33, matches requested focus (muscles)).",
              "coaching_note": "Keep range of motion pain-free; stop short of deep knee flexion.",
              "substituted_for": null
            },
            {
              "exercise_id": "0732c6eb-2275-4af3-8276-9bb8be2aa12d",
              "name": "One-Kettlebell Hamstring Walkout",
              "sets": 3,
              "reps": "8-12",
              "duration_seconds": null,
              "rest_seconds": 75,
              "rationale": "Selected from the graph-approved candidate pool (safety adjustment -50, matches requested focus (muscles)).",
              "coaching_note": "Keep range of motion pain-free; stop short of deep knee flexion.",
              "substituted_for": null
            },
            {
              "exercise_id": "03258dbf-bc21-4495-bcae-ca627b3a0f20",
              "name": "Alternating Dumbbell Overhead Press",
              "sets": 3,
              "reps": "8-12",
              "duration_seconds": null,
              "rest_seconds": 75,
              "rationale": "Selected from the graph-approved candidate pool (outside the requested focus).",
              "coaching_note": null,
              "substituted_for": null
            }
          ]
        },
        {
          "name": "cooldown",
          "exercises": [
            {
              "exercise_id": "1965072a-7e34-4d37-98f5-bde8cb6629a4",
              "name": "Cow Pose",
              "sets": 1,
              "reps": null,
              "duration_seconds": 45,
              "rest_seconds": 15,
              "rationale": "Selected from the graph-approved candidate pool (safety adjustment -8, matches requested focus (joints)).",
              "coaching_note": "Keep range of motion pain-free; stop short of deep knee flexion.",
              "substituted_for": null
            },
            {
              "exercise_id": "0a9d8d01-a52d-453e-92bc-dd9238e9a930",
              "name": "Ground Upper Trap Stretch",
              "sets": 1,
              "reps": null,
              "duration_seconds": 45,
              "rest_seconds": 15,
              "rationale": "Selected from the graph-approved candidate pool.",
              "coaching_note": null,
              "substituted_for": null
            }
          ]
        }
      ],
      "summary": null
    },
    "resolved_concepts": [
      {
        "source_text": "45-minute lower-body",
        "canonical_id": "focus:lower_body",
        "label": "Lower Body",
        "concept_type": "muscle",
        "method": "fuzzy",
        "confidence": 0.9,
        "alternatives": [
          "Lower Limb"
        ]
      },
      {
        "source_text": "left knee",
        "canonical_id": "anatomy:knee",
        "label": "Knee",
        "concept_type": "anatomy",
        "method": "alias",
        "confidence": 0.98,
        "alternatives": []
      },
      {
        "source_text": "dumbbells",
        "canonical_id": "equipment:dumbbell",
        "label": "Dumbbell",
        "concept_type": "equipment",
        "method": "alias",
        "confidence": 0.98,
        "alternatives": []
      },
      {
        "source_text": "kettlebell",
        "canonical_id": "equipment:kettlebell",
        "label": "Kettlebell",
        "concept_type": "equipment",
        "method": "exact",
        "confidence": 1.0,
        "alternatives": []
      }
    ],
    "unresolved_concepts": [],
    "filtered_exercises": [
      {
        "exercise_id": "0fa0eb42-797f-4752-9a80-68e2dfb2a935",
        "exercise": "Alternating Dumbbell Decline Bench Press",
        "decision": "filtered",
        "reasons": [
          "Requires Adjustable Bench - Decline, which Jordan Rivera does not have.",
          "Catalog lists no joints for this exercise, so it cannot be certified against the member's injury. Down-ranked as a precaution."
        ],
        "rule_ids": [
          "equipment_unavailable",
          "unknown_anatomy"
        ],
        "evidence": [
          {
            "path": [
              "Alternating Dumbbell Decline Bench Press",
              "-[REQUIRES]->",
              "Adjustable Bench - Decline"
            ],
            "rendered": "Alternating Dumbbell Decline Bench Press -[REQUIRES]-> Adjustable Bench - Decline"
          },
          {
            "path": [
              "Alternating Dumbbell Decline Bench Press"
            ],
            "rendered": "Alternating Dumbbell Decline Bench Press"
          }
        ],
        "decision_source": "knowledge_graph",
        "score": null,
        "score_adjustment": -10.0,
        "in_plan": false,
        "section": null
      },
      {
        "exercise_id": "07772057-db56-4cfb-ae4b-f98f4cac6b9a",
        "exercise": "Anchored Band Rotational Lift",
        "decision": "filtered",
        "reasons": [
          "Requires Resistance Band - With Handles, which Jordan Rivera does not have."
        ],
        "rule_ids": [
          "equipment_unavailable"
        ],
        "evidence": [
          {
            "path": [
              "Anchored Band Rotational Lift",
              "-[REQUIRES]->",
              "Resistance Band - With Handles"
            ],
            "rendered": "Anchored Band Rotational Lift -[REQUIRES]-> Resistance Band - With Handles"
          }
        ],
        "decision_source": "knowledge_graph",
        "score": null,
        "score_adjustment": 0.0,
        "in_plan": false,
        "section": null
      },
      {
        "exercise_id": "03ba2166-a5e6-4d0d-9110-ab5b73acdd50",
        "exercise": "BOSU Step Over",
        "decision": "filtered",
        "reasons": [
          "Requires BOSU, which Jordan Rivera does not have.",
          "Patellofemoral Pain Syndrome contraindicates the 'cardio - plyometric' pattern.",
          "Low-load exercise stresses knee, which is inside the region affected by Left Knee (recovering)."
        ],
        "rule_ids": [
          "equipment_unavailable",
          "injury_contraindicated_pattern",
          "injury_region_stress"
        ],
        "evidence": [
          {
            "path": [
              "BOSU Step Over",
              "-[REQUIRES]->",
              "BOSU"
            ],
            "rendered": "BOSU Step Over -[REQUIRES]-> BOSU"
          },
          {
            "path": [
              "Patellofemoral Pain Syndrome",
              "-[CONTRAINDICATES]->",
              "cardio - plyometric",
              "-[HAS_PATTERN]->",
              "BOSU Step Over"
            ],
            "rendered": "Patellofemoral Pain Syndrome -[CONTRAINDICATES]-> cardio - plyometric -[HAS_PATTERN]-> BOSU Step Over"
          },
          {
            "path": [
              "Jordan Rivera",
              "-[HAS_INJURY]->",
              "Left Knee (recovering)",
              "-[MAPS_TO]->",
              "Patellofemoral Pain Syndrome",
              "-[AFFECTS]->",
              "Patellofemoral Joint"
            ],
            "rendered": "Jordan Rivera -[HAS_INJURY]-> Left Knee (recovering) -[MAPS_TO]-> Patellofemoral Pain Syndrome -[AFFECTS]-> Patellofemoral Joint"
          },
          {
            "path": [
              "BOSU Step Over",
              "-[STRESSES]->",
              "Knee"
            ],
            "rendered": "BOSU Step Over -[STRESSES]-> Knee"
          },
          {
            "path": [
              "Patellofemoral Joint",
              "-[PART_OF]->",
              "Knee"
            ],
            "rendered": "Patellofemoral Joint -[PART_OF]-> Knee"
          },
          {
            "path": [
              "Jordan Rivera",
              "-[HAS_INJURY]->",
              "Left Knee (recovering)",
              "-[MAPS_TO]->",
              "Patellofemoral Pain Syndrome",
              "-[AFFECTS]->",
              "Patellofemoral Joint"
            ],
            "rendered": "Jordan Rivera -[HAS_INJURY]-> Left Knee (recovering) -[MAPS_TO]-> Patellofemoral Pain Syndrome -[AFFECTS]-> Patellofemoral Joint"
          }
        ],
        "decision_source": "knowledge_graph",
        "score": null,
        "score_adjustment": -8.0,
        "in_plan": false,
        "section": null
      },
      {
        "exercise_id": "0b6fcb1c-aa47-455b-8a9f-f9d1582745df",
        "exercise": "Band-Assisted Chin-Up (From Foot)",
        "decision": "filtered",
        "reasons": [
          "Requires Pull-Up Bar, which Jordan Rivera does not have."
        ],
        "rule_ids": [
          "equipment_unavailable"
        ],
        "evidence": [
          {
            "path": [
              "Band-Assisted Chin-Up (From Foot)",
              "-[REQUIRES]->",
              "Pull-Up Bar"
            ],
            "rendered": "Band-Assisted Chin-Up (From Foot) -[REQUIRES]-> Pull-Up Bar"
          }
        ],
        "decision_source": "knowledge_graph",
        "score": null,
        "score_adjustment": 0.0,
        "in_plan": false,
        "section": null
      },
      {
        "exercise_id": "00678525-7d38-4a9e-8998-a299a209c724",
        "exercise": "Alternating Dumbbell Racked Crossback Lunge",
        "decision": "downranked",
        "reasons": [
          "Patellofemoral Pain Syndrome cautions against the 'lower push - lunge' pattern; injury is mild/recovering, so this is down-ranked and needs a range-of-motion caveat rather than removed.",
          "Loaded exercise stresses knee, which is inside the region affected by Left Knee (recovering)."
        ],
        "rule_ids": [
          "injury_contraindicated_pattern",
          "injury_region_stress"
        ],
        "evidence": [
          {
            "path": [
              "Patellofemoral Pain Syndrome",
              "-[CONTRAINDICATES]->",
              "lower push - lunge",
              "-[HAS_PATTERN]->",
              "Alternating Dumbbell Racked Crossback Lunge"
            ],
            "rendered": "Patellofemoral Pain Syndrome -[CONTRAINDICATES]-> lower push - lunge -[HAS_PATTERN]-> Alternating Dumbbell Racked Crossback Lunge"
          },
          {
            "path": [
              "Jordan Rivera",
              "-[HAS_INJURY]->",
              "Left Knee (recovering)",
              "-[MAPS_TO]->",
              "Patellofemoral Pain Syndrome",
              "-[AFFECTS]->",
              "Patellofemoral Joint"
            ],
            "rendered": "Jordan Rivera -[HAS_INJURY]-> Left Knee (recovering) -[MAPS_TO]-> Patellofemoral Pain Syndrome -[AFFECTS]-> Patellofemoral Joint"
          },
          {
            "path": [
              "Alternating Dumbbell Racked Crossback Lunge",
              "-[STRESSES]->",
              "Knee"
            ],
            "rendered": "Alternating Dumbbell Racked Crossback Lunge -[STRESSES]-> Knee"
          },
          {
            "path": [
              "Patellofemoral Joint",
              "-[PART_OF]->",
              "Knee"
            ],
            "rendered": "Patellofemoral Joint -[PART_OF]-> Knee"
          },
          {
            "path": [
              "Jordan Rivera",
              "-[HAS_INJURY]->",
              "Left Knee (recovering)",
              "-[MAPS_TO]->",
              "Patellofemoral Pain Syndrome",
              "-[AFFECTS]->",
              "Patellofemoral Joint"
            ],
            "rendered": "Jordan Rivera -[HAS_INJURY]-> Left Knee (recovering) -[MAPS_TO]-> Patellofemoral Pain Syndrome -[AFFECTS]-> Patellofemoral Joint"
          }
        ],
        "decision_source": "knowledge_graph",
        "score": null,
        "score_adjustment": -90.0,
        "in_plan": false,
        "section": null
      },
      {
        "exercise_id": "02fe4cf5-bb21-4bef-868f-fea1477e2a53",
        "exercise": "Dumbbell Goblet Split Squat",
        "decision": "downranked",
        "reasons": [
          "Patellofemoral Pain Syndrome cautions against the 'lower push - split squat' pattern; injury is mild/recovering, so this is down-ranked and needs a range-of-motion caveat rather than removed.",
          "Loaded exercise stresses knee, which is inside the region affected by Left Knee (recovering).",
          "Unilateral variant loads the left side, which is the injured side (Left Knee (recovering))."
        ],
        "rule_ids": [
          "injury_contraindicated_pattern",
          "injury_region_stress",
          "injury_side_specific"
        ],
        "evidence": [
          {
            "path": [
              "Patellofemoral Pain Syndrome",
              "-[CONTRAINDICATES]->",
              "lower push - split squat",
              "-[HAS_PATTERN]->",
              "Dumbbell Goblet Split Squat"
            ],
            "rendered": "Patellofemoral Pain Syndrome -[CONTRAINDICATES]-> lower push - split squat -[HAS_PATTERN]-> Dumbbell Goblet Split Squat"
          },
          {
            "path": [
              "Jordan Rivera",
              "-[HAS_INJURY]->",
              "Left Knee (recovering)",
              "-[MAPS_TO]->",
              "Patellofemoral Pain Syndrome",
              "-[AFFECTS]->",
              "Patellofemoral Joint"
            ],
            "rendered": "Jordan Rivera -[HAS_INJURY]-> Left Knee (recovering) -[MAPS_TO]-> Patellofemoral Pain Syndrome -[AFFECTS]-> Patellofemoral Joint"
          },
          {
            "path": [
              "Dumbbell Goblet Split Squat",
              "-[STRESSES]->",
              "Knee"
            ],
            "rendered": "Dumbbell Goblet Split Squat -[STRESSES]-> Knee"
          },
          {
            "path": [
              "Patellofemoral Joint",
              "-[PART_OF]->",
              "Knee"
            ],
            "rendered": "Patellofemoral Joint -[PART_OF]-> Knee"
          },
          {
            "path": [
              "Jordan Rivera",
              "-[HAS_INJURY]->",
              "Left Knee (recovering)",
              "-[MAPS_TO]->",
              "Patellofemoral Pain Syndrome",
              "-[AFFECTS]->",
              "Patellofemoral Joint"
            ],
            "rendered": "Jordan Rivera -[HAS_INJURY]-> Left Knee (recovering) -[MAPS_TO]-> Patellofemoral Pain Syndrome -[AFFECTS]-> Patellofemoral Joint"
          },
          {
            "path": [
              "Dumbbell Goblet Split Squat"
            ],
            "rendered": "Dumbbell Goblet Split Squat"
          },
          {
            "path": [
              "Jordan Rivera",
              "-[HAS_INJURY]->",
              "Left Knee (recovering)",
              "-[MAPS_TO]->",
              "Patellofemoral Pain Syndrome",
              "-[AFFECTS]->",
              "Patellofemoral Joint"
            ],
            "rendered": "Jordan Rivera -[HAS_INJURY]-> Left Knee (recovering) -[MAPS_TO]-> Patellofemoral Pain Syndrome -[AFFECTS]-> Patellofemoral Joint"
          }
        ],
        "decision_source": "knowledge_graph",
        "score": null,
        "score_adjustment": -115.0,
        "in_plan": false,
        "section": null
      }
    ],
    "provenance": [
      {
        "exercise_id": "1423ff58-68de-47da-8884-cb6f438f5774",
        "exercise": "Walking Toe Touches",
        "decision": "included",
        "reasons": [
          "Bodyweight - no equipment required.",
          "No graph-derived contraindication against Left Knee (recovering) (Patellofemoral Pain Syndrome).",
          "matches requested focus (muscles)",
          "supports goal: \"Build lower-body strength\""
        ],
        "rule_ids": [],
        "evidence": [],
        "decision_source": "knowledge_graph",
        "score": 87.0,
        "score_adjustment": 0.0,
        "in_plan": true,
        "section": "warmup"
      },
      {
        "exercise_id": "0a4d99cf-5075-468e-9551-b9f8efa267f1",
        "exercise": "World's Greatest Stretch",
        "decision": "included",
        "reasons": [
          "Required equipment available: Yoga Mat.",
          "safety adjustment -8",
          "matches requested focus (muscles)",
          "supports goal: \"Build lower-body strength\"",
          "Low-load exercise stresses knee, which is inside the region affected by Left Knee (recovering)."
        ],
        "rule_ids": [
          "injury_region_stress"
        ],
        "evidence": [
          {
            "path": [
              "World's Greatest Stretch",
              "-[STRESSES]->",
              "Knee"
            ],
            "rendered": "World's Greatest Stretch -[STRESSES]-> Knee"
          },
          {
            "path": [
              "Patellofemoral Joint",
              "-[PART_OF]->",
              "Knee"
            ],
            "rendered": "Patellofemoral Joint -[PART_OF]-> Knee"
          },
          {
            "path": [
              "Jordan Rivera",
              "-[HAS_INJURY]->",
              "Left Knee (recovering)",
              "-[MAPS_TO]->",
              "Patellofemoral Pain Syndrome",
              "-[AFFECTS]->",
              "Patellofemoral Joint"
            ],
            "rendered": "Jordan Rivera -[HAS_INJURY]-> Left Knee (recovering) -[MAPS_TO]-> Patellofemoral Pain Syndrome -[AFFECTS]-> Patellofemoral Joint"
          }
        ],
        "decision_source": "knowledge_graph",
        "score": 79.0,
        "score_adjustment": -8.0,
        "in_plan": true,
        "section": "warmup"
      },
      {
        "exercise_id": "0a2dc786-fb42-4571-9b26-f58cdeb2c70e",
        "exercise": "Bodyweight Pike",
        "decision": "included",
        "reasons": [
          "Required equipment available: Yoga Mat.",
          "No graph-derived contraindication against Left Knee (recovering) (Patellofemoral Pain Syndrome).",
          "matches requested focus (muscles)"
        ],
        "rule_ids": [],
        "evidence": [],
        "decision_source": "knowledge_graph",
        "score": 75.0,
        "score_adjustment": 0.0,
        "in_plan": true,
        "section": "main"
      },
      {
        "exercise_id": "01f5a2bb-ecf7-4168-92b3-35bd78592e26",
        "exercise": "High Plank Bird Dog",
        "decision": "included",
        "reasons": [
          "Required equipment available: Yoga Mat.",
          "safety adjustment -8",
          "matches requested focus (joints)",
          "Low-load exercise stresses knee, which is inside the region affected by Left Knee (recovering)."
        ],
        "rule_ids": [
          "injury_region_stress"
        ],
        "evidence": [
          {
            "path": [
              "High Plank Bird Dog",
              "-[STRESSES]->",
              "Knee"
            ],
            "rendered": "High Plank Bird Dog -[STRESSES]-> Knee"
          },
          {
            "path": [
              "Patellofemoral Joint",
              "-[PART_OF]->",
              "Knee"
            ],
            "rendered": "Patellofemoral Joint -[PART_OF]-> Knee"
          },
          {
            "path": [
              "Jordan Rivera",
              "-[HAS_INJURY]->",
              "Left Knee (recovering)",
              "-[MAPS_TO]->",
              "Patellofemoral Pain Syndrome",
              "-[AFFECTS]->",
              "Patellofemoral Joint"
            ],
            "rendered": "Jordan Rivera -[HAS_INJURY]-> Left Knee (recovering) -[MAPS_TO]-> Patellofemoral Pain Syndrome -[AFFECTS]-> Patellofemoral Joint"
          }
        ],
        "decision_source": "knowledge_graph",
        "score": 57.0,
        "score_adjustment": -8.0,
        "in_plan": true,
        "section": "main"
      }
    ],
    "member_facts": [
      "Member: Jordan Rivera (1:1 Coaching).",
      "Injury: Left Knee (recovering) - mild/recovering, mapped to Patellofemoral Pain Syndrome.",
      "Equipment for this session: Dumbbell, Flat Bench, Kettlebell, Yoga Mat.",
      "Primary goal: Build lower-body strength.",
      "Dislikes (ranking only): Deadlift, Burpees."
    ],
    "safety": {
      "catalog_total": 50,
      "eligible": 16,
      "excluded": 34,
      "downranked": 7,
      "in_plan": 9,
      "post_validation_passed": true,
      "post_validation_rejections": 0,
      "post_validation_replacements": 0
    },
    "post_validation": {
      "passed": true,
      "checked_exercise_ids": [
        "1423ff58-68de-47da-8884-cb6f438f5774",
        "0a4d99cf-5075-468e-9551-b9f8efa267f1",
        "0a2dc786-fb42-4571-9b26-f58cdeb2c70e",
        "01f5a2bb-ecf7-4168-92b3-35bd78592e26",
        "02d6478f-0579-480b-a188-8e719d4fda14",
        "0732c6eb-2275-4af3-8276-9bb8be2aa12d",
        "03258dbf-bc21-4495-bcae-ca627b3a0f20",
        "1965072a-7e34-4d37-98f5-bde8cb6629a4",
        "0a9d8d01-a52d-453e-92bc-dd9238e9a930"
      ],
      "rejected": [],
      "replacements": [],
      "hallucinated_ids": [],
      "notes": []
    },
    "timings_ms": {
      "load_member": 0.01,
      "parse_intent_and_resolve": 2.48,
      "evaluate_safety": 1759.92,
      "rank_candidates": 1.09,
      "compose_workout_llm": 0.89,
      "validate_workout": 0.11,
      "build_provenance": 15.39,
      "total": 1800.12
    },
    "generator": "stub",
    "graph_backend": "neo4j",
    "graph_reasoning": {
      "trace_id": "e1ddb87eabdb",
      "graph_backend": "neo4j",
      "summary": {
        "catalog_count": 50,
        "excluded_count": 34,
        "downranked_count": 7,
        "eligible_count": 16,
        "in_plan_count": 9,
        "concepts_resolved": 4,
        "concepts_unresolved": 0,
        "traversal_count": 142,
        "exercises_with_evidence": 41,
        "counts_by_constraint": [
          {
            "constraint_type": "equipment",
            "label": "Equipment",
            "exercises_affected": 31,
            "traversals": 31
          },
          {
            "constraint_type": "injury_anatomy",
            "label": "Injury / anatomy",
            "exercises_affected": 21,
            "traversals": 81
          },
          {
            "constraint_type": "contraindication",
            "label": "Contraindication",
            "exercises_affected": 12,
            "traversals": 24
          },
          {
            "constraint_type": "data_gap",
            "label": "Missing catalog data",
            "exercises_affected": 2,
            "traversals": 2
          },
          {
            "constraint_type": "preference_ranking",
            "label": "Preference / ranking",
            "exercises_affected": 2,
            "traversals": 4
          }
        ],
        "note": "Down-ranked exercises remain eligible and may appear in the plan; these counts describe overlapping sets, not a partition."
      },
      "prompt_concepts": [
        {
          "source_text": "45-minute lower-body",
          "canonical_id": "focus:lower_body",
          "label": "Lower Body",
          "concept_type": "muscle",
          "method": "fuzzy",
          "confidence": 0.9,
          "resolved": true
        },
        {
          "source_text": "left knee",
          "canonical_id": "anatomy:knee",
          "label": "Knee",
          "concept_type": "anatomy",
          "method": "alias",
          "confidence": 0.98,
          "resolved": true
        },
        {
          "source_text": "dumbbells",
          "canonical_id": "equipment:dumbbell",
          "label": "Dumbbell",
          "concept_type": "equipment",
          "method": "alias",
          "confidence": 0.98,
          "resolved": true
        },
        {
          "source_text": "kettlebell",
          "canonical_id": "equipment:kettlebell",
          "label": "Kettlebell",
          "concept_type": "equipment",
          "method": "exact",
          "confidence": 1.0,
          "resolved": true
        }
      ],
      "traversals": [
        {
          "id": "0fa0eb42-797f-4752-9a80-68e2dfb2a935:0-0",
          "constraint_type": "equipment",
          "exercise_id": "0fa0eb42-797f-4752-9a80-68e2dfb2a935",
          "exercise_name": "Alternating Dumbbell Decline Bench Press",
          "decision": "excluded",
          "reason": "Requires Adjustable Bench - Decline, which Jordan Rivera does not have.",
          "rule_id": "equipment_unavailable",
          "source": "graph_traversal",
          "nodes": [
            {
              "id": "0fa0eb42-797f-4752-9a80-68e2dfb2a935:0-0:0",
              "label": "Alternating Dumbbell Decline Bench Press",
              "type": "Exercise",
              "properties": {}
            },
            {
              "id": "0fa0eb42-797f-4752-9a80-68e2dfb2a935:0-0:1",
              "label": "Adjustable Bench - Decline",
              "type": "Equipment",
              "properties": {}
            }
          ],
          "edges": [
            {
              "source_id": "0fa0eb42-797f-4752-9a80-68e2dfb2a935:0-0:0",
              "target_id": "0fa0eb42-797f-4752-9a80-68e2dfb2a935:0-0:1",
              "relationship": "REQUIRES",
              "direction": "outgoing",
              "rule_id": "equipment_unavailable"
            }
          ],
          "facts": [
            "Required: Adjustable Bench - Decline, Dumbbell.",
            "Available to member (Jordan Rivera): Dumbbell, Flat Bench, Kettlebell, Yoga Mat.",
            "Adjustable Bench - Decline is not in the available set."
          ],
          "source_concept": null
        },
        {
          "id": "0fa0eb42-797f-4752-9a80-68e2dfb2a935:1-0",
          "constraint_type": "data_gap",
          "exercise_id": "0fa0eb42-797f-4752-9a80-68e2dfb2a935",
          "exercise_name": "Alternating Dumbbell Decline Bench Press",
          "decision": "excluded",
          "reason": "Catalog lists no joints for this exercise, so it cannot be certified against the member's injury. Down-ranked as a precaution.",
          "rule_id": "unknown_anatomy",
          "source": "deterministic_set_operation",
          "nodes": [
            {
              "id": "0fa0eb42-797f-4752-9a80-68e2dfb2a935:1-0:0",
              "label": "Alternating Dumbbell Decline Bench Press",
              "type": "Exercise",
              "properties": {}
            }
          ],
          "edges": [],
          "facts": [
            "Catalog lists no joints_loaded for this exercise.",
            "No STRESSES edges exist, so no anatomy traversal is possible.",
            "Cannot be certified against Left Knee (recovering)."
          ],
          "source_concept": null
        },
        {
          "id": "0b6fcb1c-aa47-455b-8a9f-f9d1582745df:0-0",
          "constraint_type": "equipment",
          "exercise_id": "0b6fcb1c-aa47-455b-8a9f-f9d1582745df",
          "exercise_name": "Band-Assisted Chin-Up (From Foot)",
          "decision": "excluded",
          "reason": "Requires Pull-Up Bar, which Jordan Rivera does not have.",
          "rule_id": "equipment_unavailable",
          "source": "graph_traversal",
          "nodes": [
            {
              "id": "0b6fcb1c-aa47-455b-8a9f-f9d1582745df:0-0:0",
              "label": "Band-Assisted Chin-Up (From Foot)",
              "type": "Exercise",
              "properties": {}
            },
            {
              "id": "0b6fcb1c-aa47-455b-8a9f-f9d1582745df:0-0:1",
              "label": "Pull-Up Bar",
              "type": "Equipment",
              "properties": {}
            }
          ],
          "edges": [
            {
              "source_id": "0b6fcb1c-aa47-455b-8a9f-f9d1582745df:0-0:0",
              "target_id": "0b6fcb1c-aa47-455b-8a9f-f9d1582745df:0-0:1",
              "relationship": "REQUIRES",
              "direction": "outgoing",
              "rule_id": "equipment_unavailable"
            }
          ],
          "facts": [
            "Required: Pull-Up Bar, Resistance Band - Loop.",
            "Available to member (Jordan Rivera): Dumbbell, Flat Bench, Kettlebell, Yoga Mat.",
            "Pull-Up Bar is not in the available set."
          ],
          "source_concept": null
        },
        {
          "id": "02fe4cf5-bb21-4bef-868f-fea1477e2a53:0-0",
          "constraint_type": "contraindication",
          "exercise_id": "02fe4cf5-bb21-4bef-868f-fea1477e2a53",
          "exercise_name": "Dumbbell Goblet Split Squat",
          "decision": "downranked",
          "reason": "Patellofemoral Pain Syndrome cautions against the 'lower push - split squat' pattern; injury is mild/recovering, so this is down-ranked and needs a range-of-motion caveat rather than removed.",
          "rule_id": "injury_contraindicated_pattern",
          "source": "graph_traversal",
          "nodes": [
            {
              "id": "02fe4cf5-bb21-4bef-868f-fea1477e2a53:0-0:0",
              "label": "Patellofemoral Pain Syndrome",
              "type": "InjuryCondition",
              "properties": {}
            },
            {
              "id": "02fe4cf5-bb21-4bef-868f-fea1477e2a53:0-0:1",
              "label": "lower push - split squat",
              "type": "MovementPattern",
              "properties": {}
            },
            {
              "id": "02fe4cf5-bb21-4bef-868f-fea1477e2a53:0-0:2",
              "label": "Dumbbell Goblet Split Squat",
              "type": "Exercise",
              "properties": {}
            }
          ],
          "edges": [
            {
              "source_id": "02fe4cf5-bb21-4bef-868f-fea1477e2a53:0-0:0",
              "target_id": "02fe4cf5-bb21-4bef-868f-fea1477e2a53:0-0:1",
              "relationship": "CONTRAINDICATES",
              "direction": "outgoing",
              "rule_id": "injury_contraindicated_pattern"
            },
            {
              "source_id": "02fe4cf5-bb21-4bef-868f-fea1477e2a53:0-0:1",
              "target_id": "02fe4cf5-bb21-4bef-868f-fea1477e2a53:0-0:2",
              "relationship": "HAS_PATTERN",
              "direction": "incoming",
              "rule_id": "injury_contraindicated_pattern"
            }
          ],
          "facts": [],
          "source_concept": null
        },
        {
          "id": "02fe4cf5-bb21-4bef-868f-fea1477e2a53:0-1",
          "constraint_type": "contraindication",
          "exercise_id": "02fe4cf5-bb21-4bef-868f-fea1477e2a53",
          "exercise_name": "Dumbbell Goblet Split Squat",
          "decision": "downranked",
          "reason": "Patellofemoral Pain Syndrome cautions against the 'lower push - split squat' pattern; injury is mild/recovering, so this is down-ranked and needs a range-of-motion caveat rather than removed.",
          "rule_id": "injury_contraindicated_pattern",
          "source": "graph_traversal",
          "nodes": [
            {
              "id": "02fe4cf5-bb21-4bef-868f-fea1477e2a53:0-1:0",
              "label": "Jordan Rivera",
              "type": "Member",
              "properties": {}
            },
            {
              "id": "02fe4cf5-bb21-4bef-868f-fea1477e2a53:0-1:1",
              "label": "Left Knee (recovering)",
              "type": "Injury",
              "properties": {}
            },
            {
              "id": "02fe4cf5-bb21-4bef-868f-fea1477e2a53:0-1:2",
              "label": "Patellofemoral Pain Syndrome",
              "type": "InjuryCondition",
              "properties": {}
            },
            {
              "id": "02fe4cf5-bb21-4bef-868f-fea1477e2a53:0-1:3",
              "label": "Patellofemoral Joint",
              "type": "AnatomicalRegion",
              "properties": {}
            }
          ],
          "edges": [
            {
              "source_id": "02fe4cf5-bb21-4bef-868f-fea1477e2a53:0-1:0",
              "target_id": "02fe4cf5-bb21-4bef-868f-fea1477e2a53:0-1:1",
              "relationship": "HAS_INJURY",
              "direction": "outgoing",
              "rule_id": "injury_contraindicated_pattern"
            },
            {
              "source_id": "02fe4cf5-bb21-4bef-868f-fea1477e2a53:0-1:1",
              "target_id": "02fe4cf5-bb21-4bef-868f-fea1477e2a53:0-1:2",
              "relationship": "MAPS_TO",
              "direction": "outgoing",
              "rule_id": "injury_contraindicated_pattern"
            },
            {
              "source_id": "02fe4cf5-bb21-4bef-868f-fea1477e2a53:0-1:2",
              "target_id": "02fe4cf5-bb21-4bef-868f-fea1477e2a53:0-1:3",
              "relationship": "AFFECTS",
              "direction": "outgoing",
              "rule_id": "injury_contraindicated_pattern"
            }
          ],
          "facts": [],
          "source_concept": null
        },
        {
          "id": "02fe4cf5-bb21-4bef-868f-fea1477e2a53:1-0",
          "constraint_type": "injury_anatomy",
          "exercise_id": "02fe4cf5-bb21-4bef-868f-fea1477e2a53",
          "exercise_name": "Dumbbell Goblet Split Squat",
          "decision": "downranked",
          "reason": "Loaded exercise stresses knee, which is inside the region affected by Left Knee (recovering).",
          "rule_id": "injury_region_stress",
          "source": "graph_traversal",
          "nodes": [
            {
              "id": "02fe4cf5-bb21-4bef-868f-fea1477e2a53:1-0:0",
              "label": "Dumbbell Goblet Split Squat",
              "type": "Exercise",
              "properties": {}
            },
            {
              "id": "02fe4cf5-bb21-4bef-868f-fea1477e2a53:1-0:1",
              "label": "Knee",
              "type": "AnatomicalRegion",
              "properties": {}
            }
          ],
          "edges": [
            {
              "source_id": "02fe4cf5-bb21-4bef-868f-fea1477e2a53:1-0:0",
              "target_id": "02fe4cf5-bb21-4bef-868f-fea1477e2a53:1-0:1",
              "relationship": "STRESSES",
              "direction": "outgoing",
              "rule_id": "injury_region_stress"
            }
          ],
          "facts": [],
          "source_concept": null
        },
        {
          "id": "02fe4cf5-bb21-4bef-868f-fea1477e2a53:1-1",
          "constraint_type": "injury_anatomy",
          "exercise_id": "02fe4cf5-bb21-4bef-868f-fea1477e2a53",
          "exercise_name": "Dumbbell Goblet Split Squat",
          "decision": "downranked",
          "reason": "Loaded exercise stresses knee, which is inside the region affected by Left Knee (recovering).",
          "rule_id": "injury_region_stress",
          "source": "graph_traversal",
          "nodes": [
            {
              "id": "02fe4cf5-bb21-4bef-868f-fea1477e2a53:1-1:0",
              "label": "Patellofemoral Joint",
              "type": "AnatomicalRegion",
              "properties": {}
            },
            {
              "id": "02fe4cf5-bb21-4bef-868f-fea1477e2a53:1-1:1",
              "label": "Knee",
              "type": "AnatomicalRegion",
              "properties": {}
            }
          ],
          "edges": [
            {
              "source_id": "02fe4cf5-bb21-4bef-868f-fea1477e2a53:1-1:0",
              "target_id": "02fe4cf5-bb21-4bef-868f-fea1477e2a53:1-1:1",
              "relationship": "PART_OF",
              "direction": "outgoing",
              "rule_id": "injury_region_stress"
            }
          ],
          "facts": [],
          "source_concept": null
        },
        {
          "id": "02fe4cf5-bb21-4bef-868f-fea1477e2a53:1-2",
          "constraint_type": "injury_anatomy",
          "exercise_id": "02fe4cf5-bb21-4bef-868f-fea1477e2a53",
          "exercise_name": "Dumbbell Goblet Split Squat",
          "decision": "downranked",
          "reason": "Loaded exercise stresses knee, which is inside the region affected by Left Knee (recovering).",
          "rule_id": "injury_region_stress",
          "source": "graph_traversal",
          "nodes": [
            {
              "id": "02fe4cf5-bb21-4bef-868f-fea1477e2a53:1-2:0",
              "label": "Jordan Rivera",
              "type": "Member",
              "properties": {}
            },
            {
              "id": "02fe4cf5-bb21-4bef-868f-fea1477e2a53:1-2:1",
              "label": "Left Knee (recovering)",
              "type": "Injury",
              "properties": {}
            },
            {
              "id": "02fe4cf5-bb21-4bef-868f-fea1477e2a53:1-2:2",
              "label": "Patellofemoral Pain Syndrome",
              "type": "InjuryCondition",
              "properties": {}
            },
            {
              "id": "02fe4cf5-bb21-4bef-868f-fea1477e2a53:1-2:3",
              "label": "Patellofemoral Joint",
              "type": "AnatomicalRegion",
              "properties": {}
            }
          ],
          "edges": [
            {
              "source_id": "02fe4cf5-bb21-4bef-868f-fea1477e2a53:1-2:0",
              "target_id": "02fe4cf5-bb21-4bef-868f-fea1477e2a53:1-2:1",
              "relationship": "HAS_INJURY",
              "direction": "outgoing",
              "rule_id": "injury_region_stress"
            },
            {
              "source_id": "02fe4cf5-bb21-4bef-868f-fea1477e2a53:1-2:1",
              "target_id": "02fe4cf5-bb21-4bef-868f-fea1477e2a53:1-2:2",
              "relationship": "MAPS_TO",
              "direction": "outgoing",
              "rule_id": "injury_region_stress"
            },
            {
              "source_id": "02fe4cf5-bb21-4bef-868f-fea1477e2a53:1-2:2",
              "target_id": "02fe4cf5-bb21-4bef-868f-fea1477e2a53:1-2:3",
              "relationship": "AFFECTS",
              "direction": "outgoing",
              "rule_id": "injury_region_stress"
            }
          ],
          "facts": [],
          "source_concept": null
        },
        {
          "id": "02fe4cf5-bb21-4bef-868f-fea1477e2a53:2-0",
          "constraint_type": "injury_anatomy",
          "exercise_id": "02fe4cf5-bb21-4bef-868f-fea1477e2a53",
          "exercise_name": "Dumbbell Goblet Split Squat",
          "decision": "downranked",
          "reason": "Unilateral variant loads the left side, which is the injured side (Left Knee (recovering)).",
          "rule_id": "injury_side_specific",
          "source": "graph_traversal",
          "nodes": [
            {
              "id": "02fe4cf5-bb21-4bef-868f-fea1477e2a53:2-0:0",
              "label": "Dumbbell Goblet Split Squat",
              "type": "Exercise",
              "properties": {}
            }
          ],
          "edges": [],
          "facts": [
            "Exercise property side = left_leg.",
            "Injury laterality = left.",
            "Unilateral variant loads the injured side."
          ],
          "source_concept": null
        },
        {
          "id": "02fe4cf5-bb21-4bef-868f-fea1477e2a53:2-1",
          "constraint_type": "injury_anatomy",
          "exercise_id": "02fe4cf5-bb21-4bef-868f-fea1477e2a53",
          "exercise_name": "Dumbbell Goblet Split Squat",
          "decision": "downranked",
          "reason": "Unilateral variant loads the left side, which is the injured side (Left Knee (recovering)).",
          "rule_id": "injury_side_specific",
          "source": "graph_traversal",
          "nodes": [
            {
              "id": "02fe4cf5-bb21-4bef-868f-fea1477e2a53:2-1:0",
              "label": "Jordan Rivera",
              "type": "Member",
              "properties": {}
            },
            {
              "id": "02fe4cf5-bb21-4bef-868f-fea1477e2a53:2-1:1",
              "label": "Left Knee (recovering)",
              "type": "Injury",
              "properties": {}
            },
            {
              "id": "02fe4cf5-bb21-4bef-868f-fea1477e2a53:2-1:2",
              "label": "Patellofemoral Pain Syndrome",
              "type": "InjuryCondition",
              "properties": {}
            },
            {
              "id": "02fe4cf5-bb21-4bef-868f-fea1477e2a53:2-1:3",
              "label": "Patellofemoral Joint",
              "type": "AnatomicalRegion",
              "properties": {}
            }
          ],
          "edges": [
            {
              "source_id": "02fe4cf5-bb21-4bef-868f-fea1477e2a53:2-1:0",
              "target_id": "02fe4cf5-bb21-4bef-868f-fea1477e2a53:2-1:1",
              "relationship": "HAS_INJURY",
              "direction": "outgoing",
              "rule_id": "injury_side_specific"
            },
            {
              "source_id": "02fe4cf5-bb21-4bef-868f-fea1477e2a53:2-1:1",
              "target_id": "02fe4cf5-bb21-4bef-868f-fea1477e2a53:2-1:2",
              "relationship": "MAPS_TO",
              "direction": "outgoing",
              "rule_id": "injury_side_specific"
            },
            {
              "source_id": "02fe4cf5-bb21-4bef-868f-fea1477e2a53:2-1:2",
              "target_id": "02fe4cf5-bb21-4bef-868f-fea1477e2a53:2-1:3",
              "relationship": "AFFECTS",
              "direction": "outgoing",
              "rule_id": "injury_side_specific"
            }
          ],
          "facts": [],
          "source_concept": null
        },
        {
          "id": "0a4d99cf-5075-468e-9551-b9f8efa267f1:0-0",
          "constraint_type": "injury_anatomy",
          "exercise_id": "0a4d99cf-5075-468e-9551-b9f8efa267f1",
          "exercise_name": "World's Greatest Stretch",
          "decision": "downranked",
          "reason": "Low-load exercise stresses knee, which is inside the region affected by Left Knee (recovering).",
          "rule_id": "injury_region_stress",
          "source": "graph_traversal",
          "nodes": [
            {
              "id": "0a4d99cf-5075-468e-9551-b9f8efa267f1:0-0:0",
              "label": "World's Greatest Stretch",
              "type": "Exercise",
              "properties": {}
            },
            {
              "id": "0a4d99cf-5075-468e-9551-b9f8efa267f1:0-0:1",
              "label": "Knee",
              "type": "AnatomicalRegion",
              "properties": {}
            }
          ],
          "edges": [
            {
              "source_id": "0a4d99cf-5075-468e-9551-b9f8efa267f1:0-0:0",
              "target_id": "0a4d99cf-5075-468e-9551-b9f8efa267f1:0-0:1",
              "relationship": "STRESSES",
              "direction": "outgoing",
              "rule_id": "injury_region_stress"
            }
          ],
          "facts": [],
          "source_concept": null
        },
        {
          "id": "0a4d99cf-5075-468e-9551-b9f8efa267f1:0-1",
          "constraint_type": "injury_anatomy",
          "exercise_id": "0a4d99cf-5075-468e-9551-b9f8efa267f1",
          "exercise_name": "World's Greatest Stretch",
          "decision": "downranked",
          "reason": "Low-load exercise stresses knee, which is inside the region affected by Left Knee (recovering).",
          "rule_id": "injury_region_stress",
          "source": "graph_traversal",
          "nodes": [
            {
              "id": "0a4d99cf-5075-468e-9551-b9f8efa267f1:0-1:0",
              "label": "Patellofemoral Joint",
              "type": "AnatomicalRegion",
              "properties": {}
            },
            {
              "id": "0a4d99cf-5075-468e-9551-b9f8efa267f1:0-1:1",
              "label": "Knee",
              "type": "AnatomicalRegion",
              "properties": {}
            }
          ],
          "edges": [
            {
              "source_id": "0a4d99cf-5075-468e-9551-b9f8efa267f1:0-1:0",
              "target_id": "0a4d99cf-5075-468e-9551-b9f8efa267f1:0-1:1",
              "relationship": "PART_OF",
              "direction": "outgoing",
              "rule_id": "injury_region_stress"
            }
          ],
          "facts": [],
          "source_concept": null
        },
        {
          "id": "0a4d99cf-5075-468e-9551-b9f8efa267f1:0-2",
          "constraint_type": "injury_anatomy",
          "exercise_id": "0a4d99cf-5075-468e-9551-b9f8efa267f1",
          "exercise_name": "World's Greatest Stretch",
          "decision": "downranked",
          "reason": "Low-load exercise stresses knee, which is inside the region affected by Left Knee (recovering).",
          "rule_id": "injury_region_stress",
          "source": "graph_traversal",
          "nodes": [
            {
              "id": "0a4d99cf-5075-468e-9551-b9f8efa267f1:0-2:0",
              "label": "Jordan Rivera",
              "type": "Member",
              "properties": {}
            },
            {
              "id": "0a4d99cf-5075-468e-9551-b9f8efa267f1:0-2:1",
              "label": "Left Knee (recovering)",
              "type": "Injury",
              "properties": {}
            },
            {
              "id": "0a4d99cf-5075-468e-9551-b9f8efa267f1:0-2:2",
              "label": "Patellofemoral Pain Syndrome",
              "type": "InjuryCondition",
              "properties": {}
            },
            {
              "id": "0a4d99cf-5075-468e-9551-b9f8efa267f1:0-2:3",
              "label": "Patellofemoral Joint",
              "type": "AnatomicalRegion",
              "properties": {}
            }
          ],
          "edges": [
            {
              "source_id": "0a4d99cf-5075-468e-9551-b9f8efa267f1:0-2:0",
              "target_id": "0a4d99cf-5075-468e-9551-b9f8efa267f1:0-2:1",
              "relationship": "HAS_INJURY",
              "direction": "outgoing",
              "rule_id": "injury_region_stress"
            },
            {
              "source_id": "0a4d99cf-5075-468e-9551-b9f8efa267f1:0-2:1",
              "target_id": "0a4d99cf-5075-468e-9551-b9f8efa267f1:0-2:2",
              "relationship": "MAPS_TO",
              "direction": "outgoing",
              "rule_id": "injury_region_stress"
            },
            {
              "source_id": "0a4d99cf-5075-468e-9551-b9f8efa267f1:0-2:2",
              "target_id": "0a4d99cf-5075-468e-9551-b9f8efa267f1:0-2:3",
              "relationship": "AFFECTS",
              "direction": "outgoing",
              "rule_id": "injury_region_stress"
            }
          ],
          "facts": [],
          "source_concept": null
        },
        {
          "id": "00678525-7d38-4a9e-8998-a299a209c724:0-0",
          "constraint_type": "contraindication",
          "exercise_id": "00678525-7d38-4a9e-8998-a299a209c724",
          "exercise_name": "Alternating Dumbbell Racked Crossback Lunge",
          "decision": "downranked",
          "reason": "Patellofemoral Pain Syndrome cautions against the 'lower push - lunge' pattern; injury is mild/recovering, so this is down-ranked and needs a range-of-motion caveat rather than removed.",
          "rule_id": "injury_contraindicated_pattern",
          "source": "graph_traversal",
          "nodes": [
            {
              "id": "00678525-7d38-4a9e-8998-a299a209c724:0-0:0",
              "label": "Patellofemoral Pain Syndrome",
              "type": "InjuryCondition",
              "properties": {}
            },
            {
              "id": "00678525-7d38-4a9e-8998-a299a209c724:0-0:1",
              "label": "lower push - lunge",
              "type": "MovementPattern",
              "properties": {}
            },
            {
              "id": "00678525-7d38-4a9e-8998-a299a209c724:0-0:2",
              "label": "Alternating Dumbbell Racked Crossback Lunge",
              "type": "Exercise",
              "properties": {}
            }
          ],
          "edges": [
            {
              "source_id": "00678525-7d38-4a9e-8998-a299a209c724:0-0:0",
              "target_id": "00678525-7d38-4a9e-8998-a299a209c724:0-0:1",
              "relationship": "CONTRAINDICATES",
              "direction": "outgoing",
              "rule_id": "injury_contraindicated_pattern"
            },
            {
              "source_id": "00678525-7d38-4a9e-8998-a299a209c724:0-0:1",
              "target_id": "00678525-7d38-4a9e-8998-a299a209c724:0-0:2",
              "relationship": "HAS_PATTERN",
              "direction": "incoming",
              "rule_id": "injury_contraindicated_pattern"
            }
          ],
          "facts": [],
          "source_concept": null
        },
        {
          "id": "00678525-7d38-4a9e-8998-a299a209c724:0-1",
          "constraint_type": "contraindication",
          "exercise_id": "00678525-7d38-4a9e-8998-a299a209c724",
          "exercise_name": "Alternating Dumbbell Racked Crossback Lunge",
          "decision": "downranked",
          "reason": "Patellofemoral Pain Syndrome cautions against the 'lower push - lunge' pattern; injury is mild/recovering, so this is down-ranked and needs a range-of-motion caveat rather than removed.",
          "rule_id": "injury_contraindicated_pattern",
          "source": "graph_traversal",
          "nodes": [
            {
              "id": "00678525-7d38-4a9e-8998-a299a209c724:0-1:0",
              "label": "Jordan Rivera",
              "type": "Member",
              "properties": {}
            },
            {
              "id": "00678525-7d38-4a9e-8998-a299a209c724:0-1:1",
              "label": "Left Knee (recovering)",
              "type": "Injury",
              "properties": {}
            },
            {
              "id": "00678525-7d38-4a9e-8998-a299a209c724:0-1:2",
              "label": "Patellofemoral Pain Syndrome",
              "type": "InjuryCondition",
              "properties": {}
            },
            {
              "id": "00678525-7d38-4a9e-8998-a299a209c724:0-1:3",
              "label": "Patellofemoral Joint",
              "type": "AnatomicalRegion",
              "properties": {}
            }
          ],
          "edges": [
            {
              "source_id": "00678525-7d38-4a9e-8998-a299a209c724:0-1:0",
              "target_id": "00678525-7d38-4a9e-8998-a299a209c724:0-1:1",
              "relationship": "HAS_INJURY",
              "direction": "outgoing",
              "rule_id": "injury_contraindicated_pattern"
            },
            {
              "source_id": "00678525-7d38-4a9e-8998-a299a209c724:0-1:1",
              "target_id": "00678525-7d38-4a9e-8998-a299a209c724:0-1:2",
              "relationship": "MAPS_TO",
              "direction": "outgoing",
              "rule_id": "injury_contraindicated_pattern"
            },
            {
              "source_id": "00678525-7d38-4a9e-8998-a299a209c724:0-1:2",
              "target_id": "00678525-7d38-4a9e-8998-a299a209c724:0-1:3",
              "relationship": "AFFECTS",
              "direction": "outgoing",
              "rule_id": "injury_contraindicated_pattern"
            }
          ],
          "facts": [],
          "source_concept": null
        },
        {
          "id": "00678525-7d38-4a9e-8998-a299a209c724:1-0",
          "constraint_type": "injury_anatomy",
          "exercise_id": "00678525-7d38-4a9e-8998-a299a209c724",
          "exercise_name": "Alternating Dumbbell Racked Crossback Lunge",
          "decision": "downranked",
          "reason": "Loaded exercise stresses knee, which is inside the region affected by Left Knee (recovering).",
          "rule_id": "injury_region_stress",
          "source": "graph_traversal",
          "nodes": [
            {
              "id": "00678525-7d38-4a9e-8998-a299a209c724:1-0:0",
              "label": "Alternating Dumbbell Racked Crossback Lunge",
              "type": "Exercise",
              "properties": {}
            },
            {
              "id": "00678525-7d38-4a9e-8998-a299a209c724:1-0:1",
              "label": "Knee",
              "type": "AnatomicalRegion",
              "properties": {}
            }
          ],
          "edges": [
            {
              "source_id": "00678525-7d38-4a9e-8998-a299a209c724:1-0:0",
              "target_id": "00678525-7d38-4a9e-8998-a299a209c724:1-0:1",
              "relationship": "STRESSES",
              "direction": "outgoing",
              "rule_id": "injury_region_stress"
            }
          ],
          "facts": [],
          "source_concept": null
        },
        {
          "id": "00678525-7d38-4a9e-8998-a299a209c724:1-1",
          "constraint_type": "injury_anatomy",
          "exercise_id": "00678525-7d38-4a9e-8998-a299a209c724",
          "exercise_name": "Alternating Dumbbell Racked Crossback Lunge",
          "decision": "downranked",
          "reason": "Loaded exercise stresses knee, which is inside the region affected by Left Knee (recovering).",
          "rule_id": "injury_region_stress",
          "source": "graph_traversal",
          "nodes": [
            {
              "id": "00678525-7d38-4a9e-8998-a299a209c724:1-1:0",
              "label": "Patellofemoral Joint",
              "type": "AnatomicalRegion",
              "properties": {}
            },
            {
              "id": "00678525-7d38-4a9e-8998-a299a209c724:1-1:1",
              "label": "Knee",
              "type": "AnatomicalRegion",
              "properties": {}
            }
          ],
          "edges": [
            {
              "source_id": "00678525-7d38-4a9e-8998-a299a209c724:1-1:0",
              "target_id": "00678525-7d38-4a9e-8998-a299a209c724:1-1:1",
              "relationship": "PART_OF",
              "direction": "outgoing",
              "rule_id": "injury_region_stress"
            }
          ],
          "facts": [],
          "source_concept": null
        },
        {
          "id": "00678525-7d38-4a9e-8998-a299a209c724:1-2",
          "constraint_type": "injury_anatomy",
          "exercise_id": "00678525-7d38-4a9e-8998-a299a209c724",
          "exercise_name": "Alternating Dumbbell Racked Crossback Lunge",
          "decision": "downranked",
          "reason": "Loaded exercise stresses knee, which is inside the region affected by Left Knee (recovering).",
          "rule_id": "injury_region_stress",
          "source": "graph_traversal",
          "nodes": [
            {
              "id": "00678525-7d38-4a9e-8998-a299a209c724:1-2:0",
              "label": "Jordan Rivera",
              "type": "Member",
              "properties": {}
            },
            {
              "id": "00678525-7d38-4a9e-8998-a299a209c724:1-2:1",
              "label": "Left Knee (recovering)",
              "type": "Injury",
              "properties": {}
            },
            {
              "id": "00678525-7d38-4a9e-8998-a299a209c724:1-2:2",
              "label": "Patellofemoral Pain Syndrome",
              "type": "InjuryCondition",
              "properties": {}
            },
            {
              "id": "00678525-7d38-4a9e-8998-a299a209c724:1-2:3",
              "label": "Patellofemoral Joint",
              "type": "AnatomicalRegion",
              "properties": {}
            }
          ],
          "edges": [
            {
              "source_id": "00678525-7d38-4a9e-8998-a299a209c724:1-2:0",
              "target_id": "00678525-7d38-4a9e-8998-a299a209c724:1-2:1",
              "relationship": "HAS_INJURY",
              "direction": "outgoing",
              "rule_id": "injury_region_stress"
            },
            {
              "source_id": "00678525-7d38-4a9e-8998-a299a209c724:1-2:1",
              "target_id": "00678525-7d38-4a9e-8998-a299a209c724:1-2:2",
              "relationship": "MAPS_TO",
              "direction": "outgoing",
              "rule_id": "injury_region_stress"
            },
            {
              "source_id": "00678525-7d38-4a9e-8998-a299a209c724:1-2:2",
              "target_id": "00678525-7d38-4a9e-8998-a299a209c724:1-2:3",
              "relationship": "AFFECTS",
              "direction": "outgoing",
              "rule_id": "injury_region_stress"
            }
          ],
          "facts": [],
          "source_concept": null
        },
        {
          "id": "01f5a2bb-ecf7-4168-92b3-35bd78592e26:0-0",
          "constraint_type": "injury_anatomy",
          "exercise_id": "01f5a2bb-ecf7-4168-92b3-35bd78592e26",
          "exercise_name": "High Plank Bird Dog",
          "decision": "downranked",
          "reason": "Low-load exercise stresses knee, which is inside the region affected by Left Knee (recovering).",
          "rule_id": "injury_region_stress",
          "source": "graph_traversal",
          "nodes": [
            {
              "id": "01f5a2bb-ecf7-4168-92b3-35bd78592e26:0-0:0",
              "label": "High Plank Bird Dog",
              "type": "Exercise",
              "properties": {}
            },
            {
              "id": "01f5a2bb-ecf7-4168-92b3-35bd78592e26:0-0:1",
              "label": "Knee",
              "type": "AnatomicalRegion",
              "properties": {}
            }
          ],
          "edges": [
            {
              "source_id": "01f5a2bb-ecf7-4168-92b3-35bd78592e26:0-0:0",
              "target_id": "01f5a2bb-ecf7-4168-92b3-35bd78592e26:0-0:1",
              "relationship": "STRESSES",
              "direction": "outgoing",
              "rule_id": "injury_region_stress"
            }
          ],
          "facts": [],
          "source_concept": null
        },
        {
          "id": "01f5a2bb-ecf7-4168-92b3-35bd78592e26:0-1",
          "constraint_type": "injury_anatomy",
          "exercise_id": "01f5a2bb-ecf7-4168-92b3-35bd78592e26",
          "exercise_name": "High Plank Bird Dog",
          "decision": "downranked",
          "reason": "Low-load exercise stresses knee, which is inside the region affected by Left Knee (recovering).",
          "rule_id": "injury_region_stress",
          "source": "graph_traversal",
          "nodes": [
            {
              "id": "01f5a2bb-ecf7-4168-92b3-35bd78592e26:0-1:0",
              "label": "Patellofemoral Joint",
              "type": "AnatomicalRegion",
              "properties": {}
            },
            {
              "id": "01f5a2bb-ecf7-4168-92b3-35bd78592e26:0-1:1",
              "label": "Knee",
              "type": "AnatomicalRegion",
              "properties": {}
            }
          ],
          "edges": [
            {
              "source_id": "01f5a2bb-ecf7-4168-92b3-35bd78592e26:0-1:0",
              "target_id": "01f5a2bb-ecf7-4168-92b3-35bd78592e26:0-1:1",
              "relationship": "PART_OF",
              "direction": "outgoing",
              "rule_id": "injury_region_stress"
            }
          ],
          "facts": [],
          "source_concept": null
        },
        {
          "id": "01f5a2bb-ecf7-4168-92b3-35bd78592e26:0-2",
          "constraint_type": "injury_anatomy",
          "exercise_id": "01f5a2bb-ecf7-4168-92b3-35bd78592e26",
          "exercise_name": "High Plank Bird Dog",
          "decision": "downranked",
          "reason": "Low-load exercise stresses knee, which is inside the region affected by Left Knee (recovering).",
          "rule_id": "injury_region_stress",
          "source": "graph_traversal",
          "nodes": [
            {
              "id": "01f5a2bb-ecf7-4168-92b3-35bd78592e26:0-2:0",
              "label": "Jordan Rivera",
              "type": "Member",
              "properties": {}
            },
            {
              "id": "01f5a2bb-ecf7-4168-92b3-35bd78592e26:0-2:1",
              "label": "Left Knee (recovering)",
              "type": "Injury",
              "properties": {}
            },
            {
              "id": "01f5a2bb-ecf7-4168-92b3-35bd78592e26:0-2:2",
              "label": "Patellofemoral Pain Syndrome",
              "type": "InjuryCondition",
              "properties": {}
            },
            {
              "id": "01f5a2bb-ecf7-4168-92b3-35bd78592e26:0-2:3",
              "label": "Patellofemoral Joint",
              "type": "AnatomicalRegion",
              "properties": {}
            }
          ],
          "edges": [
            {
              "source_id": "01f5a2bb-ecf7-4168-92b3-35bd78592e26:0-2:0",
              "target_id": "01f5a2bb-ecf7-4168-92b3-35bd78592e26:0-2:1",
              "relationship": "HAS_INJURY",
              "direction": "outgoing",
              "rule_id": "injury_region_stress"
            },
            {
              "source_id": "01f5a2bb-ecf7-4168-92b3-35bd78592e26:0-2:1",
              "target_id": "01f5a2bb-ecf7-4168-92b3-35bd78592e26:0-2:2",
              "relationship": "MAPS_TO",
              "direction": "outgoing",
              "rule_id": "injury_region_stress"
            },
            {
              "source_id": "01f5a2bb-ecf7-4168-92b3-35bd78592e26:0-2:2",
              "target_id": "01f5a2bb-ecf7-4168-92b3-35bd78592e26:0-2:3",
              "relationship": "AFFECTS",
              "direction": "outgoing",
              "rule_id": "injury_region_stress"
            }
          ],
          "facts": [],
          "source_concept": null
        },
        {
          "id": "03ba2166-a5e6-4d0d-9110-ab5b73acdd50:0-0",
          "constraint_type": "equipment",
          "exercise_id": "03ba2166-a5e6-4d0d-9110-ab5b73acdd50",
          "exercise_name": "BOSU Step Over",
          "decision": "excluded",
          "reason": "Requires BOSU, which Jordan Rivera does not have.",
          "rule_id": "equipment_unavailable",
          "source": "graph_traversal",
          "nodes": [
            {
              "id": "03ba2166-a5e6-4d0d-9110-ab5b73acdd50:0-0:0",
              "label": "BOSU Step Over",
              "type": "Exercise",
              "properties": {}
            },
            {
              "id": "03ba2166-a5e6-4d0d-9110-ab5b73acdd50:0-0:1",
              "label": "BOSU",
              "type": "Equipment",
              "properties": {}
            }
          ],
          "edges": [
            {
              "source_id": "03ba2166-a5e6-4d0d-9110-ab5b73acdd50:0-0:0",
              "target_id": "03ba2166-a5e6-4d0d-9110-ab5b73acdd50:0-0:1",
              "relationship": "REQUIRES",
              "direction": "outgoing",
              "rule_id": "equipment_unavailable"
            }
          ],
          "facts": [
            "Required: BOSU.",
            "Available to member (Jordan Rivera): Dumbbell, Flat Bench, Kettlebell, Yoga Mat.",
            "BOSU is not in the available set."
          ],
          "source_concept": null
        },
        {
          "id": "03ba2166-a5e6-4d0d-9110-ab5b73acdd50:1-0",
          "constraint_type": "contraindication",
          "exercise_id": "03ba2166-a5e6-4d0d-9110-ab5b73acdd50",
          "exercise_name": "BOSU Step Over",
          "decision": "excluded",
          "reason": "Patellofemoral Pain Syndrome contraindicates the 'cardio - plyometric' pattern.",
          "rule_id": "injury_contraindicated_pattern",
          "source": "graph_traversal",
          "nodes": [
            {
              "id": "03ba2166-a5e6-4d0d-9110-ab5b73acdd50:1-0:0",
              "label": "Patellofemoral Pain Syndrome",
              "type": "InjuryCondition",
              "properties": {}
            },
            {
              "id": "03ba2166-a5e6-4d0d-9110-ab5b73acdd50:1-0:1",
              "label": "cardio - plyometric",
              "type": "MovementPattern",
              "properties": {}
            },
            {
              "id": "03ba2166-a5e6-4d0d-9110-ab5b73acdd50:1-0:2",
              "label": "BOSU Step Over",
              "type": "Exercise",
              "properties": {}
            }
          ],
          "edges": [
            {
              "source_id": "03ba2166-a5e6-4d0d-9110-ab5b73acdd50:1-0:0",
              "target_id": "03ba2166-a5e6-4d0d-9110-ab5b73acdd50:1-0:1",
              "relationship": "CONTRAINDICATES",
              "direction": "outgoing",
              "rule_id": "injury_contraindicated_pattern"
            },
            {
              "source_id": "03ba2166-a5e6-4d0d-9110-ab5b73acdd50:1-0:1",
              "target_id": "03ba2166-a5e6-4d0d-9110-ab5b73acdd50:1-0:2",
              "relationship": "HAS_PATTERN",
              "direction": "incoming",
              "rule_id": "injury_contraindicated_pattern"
            }
          ],
          "facts": [],
          "source_concept": null
        },
        {
          "id": "03ba2166-a5e6-4d0d-9110-ab5b73acdd50:1-1",
          "constraint_type": "contraindication",
          "exercise_id": "03ba2166-a5e6-4d0d-9110-ab5b73acdd50",
          "exercise_name": "BOSU Step Over",
          "decision": "excluded",
          "reason": "Patellofemoral Pain Syndrome contraindicates the 'cardio - plyometric' pattern.",
          "rule_id": "injury_contraindicated_pattern",
          "source": "graph_traversal",
          "nodes": [
            {
              "id": "03ba2166-a5e6-4d0d-9110-ab5b73acdd50:1-1:0",
              "label": "Jordan Rivera",
              "type": "Member",
              "properties": {}
            },
            {
              "id": "03ba2166-a5e6-4d0d-9110-ab5b73acdd50:1-1:1",
              "label": "Left Knee (recovering)",
              "type": "Injury",
              "properties": {}
            },
            {
              "id": "03ba2166-a5e6-4d0d-9110-ab5b73acdd50:1-1:2",
              "label": "Patellofemoral Pain Syndrome",
              "type": "InjuryCondition",
              "properties": {}
            },
            {
              "id": "03ba2166-a5e6-4d0d-9110-ab5b73acdd50:1-1:3",
              "label": "Patellofemoral Joint",
              "type": "AnatomicalRegion",
              "properties": {}
            }
          ],
          "edges": [
            {
              "source_id": "03ba2166-a5e6-4d0d-9110-ab5b73acdd50:1-1:0",
              "target_id": "03ba2166-a5e6-4d0d-9110-ab5b73acdd50:1-1:1",
              "relationship": "HAS_INJURY",
              "direction": "outgoing",
              "rule_id": "injury_contraindicated_pattern"
            },
            {
              "source_id": "03ba2166-a5e6-4d0d-9110-ab5b73acdd50:1-1:1",
              "target_id": "03ba2166-a5e6-4d0d-9110-ab5b73acdd50:1-1:2",
              "relationship": "MAPS_TO",
              "direction": "outgoing",
              "rule_id": "injury_contraindicated_pattern"
            },
            {
              "source_id": "03ba2166-a5e6-4d0d-9110-ab5b73acdd50:1-1:2",
              "target_id": "03ba2166-a5e6-4d0d-9110-ab5b73acdd50:1-1:3",
              "relationship": "AFFECTS",
              "direction": "outgoing",
              "rule_id": "injury_contraindicated_pattern"
            }
          ],
          "facts": [],
          "source_concept": null
        },
        {
          "id": "03ba2166-a5e6-4d0d-9110-ab5b73acdd50:2-0",
          "constraint_type": "injury_anatomy",
          "exercise_id": "03ba2166-a5e6-4d0d-9110-ab5b73acdd50",
          "exercise_name": "BOSU Step Over",
          "decision": "excluded",
          "reason": "Low-load exercise stresses knee, which is inside the region affected by Left Knee (recovering).",
          "rule_id": "injury_region_stress",
          "source": "graph_traversal",
          "nodes": [
            {
              "id": "03ba2166-a5e6-4d0d-9110-ab5b73acdd50:2-0:0",
              "label": "BOSU Step Over",
              "type": "Exercise",
              "properties": {}
            },
            {
              "id": "03ba2166-a5e6-4d0d-9110-ab5b73acdd50:2-0:1",
              "label": "Knee",
              "type": "AnatomicalRegion",
              "properties": {}
            }
          ],
          "edges": [
            {
              "source_id": "03ba2166-a5e6-4d0d-9110-ab5b73acdd50:2-0:0",
              "target_id": "03ba2166-a5e6-4d0d-9110-ab5b73acdd50:2-0:1",
              "relationship": "STRESSES",
              "direction": "outgoing",
              "rule_id": "injury_region_stress"
            }
          ],
          "facts": [],
          "source_concept": null
        },
        {
          "id": "03ba2166-a5e6-4d0d-9110-ab5b73acdd50:2-1",
          "constraint_type": "injury_anatomy",
          "exercise_id": "03ba2166-a5e6-4d0d-9110-ab5b73acdd50",
          "exercise_name": "BOSU Step Over",
          "decision": "excluded",
          "reason": "Low-load exercise stresses knee, which is inside the region affected by Left Knee (recovering).",
          "rule_id": "injury_region_stress",
          "source": "graph_traversal",
          "nodes": [
            {
              "id": "03ba2166-a5e6-4d0d-9110-ab5b73acdd50:2-1:0",
              "label": "Patellofemoral Joint",
              "type": "AnatomicalRegion",
              "properties": {}
            },
            {
              "id": "03ba2166-a5e6-4d0d-9110-ab5b73acdd50:2-1:1",
              "label": "Knee",
              "type": "AnatomicalRegion",
              "properties": {}
            }
          ],
          "edges": [
            {
              "source_id": "03ba2166-a5e6-4d0d-9110-ab5b73acdd50:2-1:0",
              "target_id": "03ba2166-a5e6-4d0d-9110-ab5b73acdd50:2-1:1",
              "relationship": "PART_OF",
              "direction": "outgoing",
              "rule_id": "injury_region_stress"
            }
          ],
          "facts": [],
          "source_concept": null
        },
        {
          "id": "03ba2166-a5e6-4d0d-9110-ab5b73acdd50:2-2",
          "constraint_type": "injury_anatomy",
          "exercise_id": "03ba2166-a5e6-4d0d-9110-ab5b73acdd50",
          "exercise_name": "BOSU Step Over",
          "decision": "excluded",
          "reason": "Low-load exercise stresses knee, which is inside the region affected by Left Knee (recovering).",
          "rule_id": "injury_region_stress",
          "source": "graph_traversal",
          "nodes": [
            {
              "id": "03ba2166-a5e6-4d0d-9110-ab5b73acdd50:2-2:0",
              "label": "Jordan Rivera",
              "type": "Member",
              "properties": {}
            },
            {
              "id": "03ba2166-a5e6-4d0d-9110-ab5b73acdd50:2-2:1",
              "label": "Left Knee (recovering)",
              "type": "Injury",
              "properties": {}
            },
            {
              "id": "03ba2166-a5e6-4d0d-9110-ab5b73acdd50:2-2:2",
              "label": "Patellofemoral Pain Syndrome",
              "type": "InjuryCondition",
              "properties": {}
            },
            {
              "id": "03ba2166-a5e6-4d0d-9110-ab5b73acdd50:2-2:3",
              "label": "Patellofemoral Joint",
              "type": "AnatomicalRegion",
              "properties": {}
            }
          ],
          "edges": [
            {
              "source_id": "03ba2166-a5e6-4d0d-9110-ab5b73acdd50:2-2:0",
              "target_id": "03ba2166-a5e6-4d0d-9110-ab5b73acdd50:2-2:1",
              "relationship": "HAS_INJURY",
              "direction": "outgoing",
              "rule_id": "injury_region_stress"
            },
            {
              "source_id": "03ba2166-a5e6-4d0d-9110-ab5b73acdd50:2-2:1",
              "target_id": "03ba2166-a5e6-4d0d-9110-ab5b73acdd50:2-2:2",
              "relationship": "MAPS_TO",
              "direction": "outgoing",
              "rule_id": "injury_region_stress"
            },
            {
              "source_id": "03ba2166-a5e6-4d0d-9110-ab5b73acdd50:2-2:2",
              "target_id": "03ba2166-a5e6-4d0d-9110-ab5b73acdd50:2-2:3",
              "relationship": "AFFECTS",
              "direction": "outgoing",
              "rule_id": "injury_region_stress"
            }
          ],
          "facts": [],
          "source_concept": null
        },
        {
          "id": "07772057-db56-4cfb-ae4b-f98f4cac6b9a:0-0",
          "constraint_type": "equipment",
          "exercise_id": "07772057-db56-4cfb-ae4b-f98f4cac6b9a",
          "exercise_name": "Anchored Band Rotational Lift",
          "decision": "excluded",
          "reason": "Requires Resistance Band - With Handles, which Jordan Rivera does not have.",
          "rule_id": "equipment_unavailable",
          "source": "graph_traversal",
          "nodes": [
            {
              "id": "07772057-db56-4cfb-ae4b-f98f4cac6b9a:0-0:0",
              "label": "Anchored Band Rotational Lift",
              "type": "Exercise",
              "properties": {}
            },
            {
              "id": "07772057-db56-4cfb-ae4b-f98f4cac6b9a:0-0:1",
              "label": "Resistance Band - With Handles",
              "type": "Equipment",
              "properties": {}
            }
          ],
          "edges": [
            {
              "source_id": "07772057-db56-4cfb-ae4b-f98f4cac6b9a:0-0:0",
              "target_id": "07772057-db56-4cfb-ae4b-f98f4cac6b9a:0-0:1",
              "relationship": "REQUIRES",
              "direction": "outgoing",
              "rule_id": "equipment_unavailable"
            }
          ],
          "facts": [
            "Required: Resistance Band - With Handles.",
            "Available to member (Jordan Rivera): Dumbbell, Flat Bench, Kettlebell, Yoga Mat.",
            "Resistance Band - With Handles is not in the available set."
          ],
          "source_concept": null
        }
      ],
      "member_facts": [
        "Member: Jordan Rivera (1:1 Coaching).",
        "Injury: Left Knee (recovering) - mild/recovering, mapped to Patellofemoral Pain Syndrome.",
        "Equipment for this session: Dumbbell, Flat Bench, Kettlebell, Yoga Mat.",
        "Primary goal: Build lower-body strength.",
        "Dislikes (ranking only): Deadlift, Burpees."
      ]
    }
  },
  "copilot": {
    "intent": "ADHERENCE_TREND",
    "answer": "Jordan's weekly completion went from 100.0% to 50.0% across 4 weeks (declining, -50 points).",
    "citations": [
      {
        "source": "Member graph: AdherenceObservation",
        "detail": "4 weekly observations (2026-05-12 to 2026-06-02)"
      }
    ],
    "chart": {
      "type": "line",
      "title": "Weekly adherence",
      "x": [
        "Week of 2026-05-12",
        "Week of 2026-05-19",
        "Week of 2026-05-26",
        "Week of 2026-06-02"
      ],
      "series": [
        {
          "name": "Completion %",
          "values": [
            100.0,
            100.0,
            75.0,
            50.0
          ]
        }
      ],
      "y_label": "%",
      "y_domain": [
        0.0,
        100.0
      ]
    },
    "evidence": {
      "metric": "weekly_completion_pct",
      "weeks": [
        "2026-05-12",
        "2026-05-19",
        "2026-05-26",
        "2026-06-02"
      ],
      "values": [
        100.0,
        100.0,
        75.0,
        50.0
      ],
      "latest_pct": 50.0,
      "first_pct": 100.0,
      "delta_pct": -50.0,
      "direction": "declining",
      "average_pct": 81.2,
      "recorded_trend_label": "declining",
      "summary": "Jordan's weekly completion went from 100.0% to 50.0% across 4 weeks (declining, -50 points)."
    },
    "generator": "stub",
    "latency_ms": 0.39
  }
} as const;

/**
 * An MCP-grounded safety answer, captured verbatim from
 * "Can Jordan do Static Jump today?".
 *
 * `evidence` is deliberately left empty here: the raw tool payloads exist on
 * the real response, but no component may depend on them to render, and a test
 * that fed them in could not prove that.
 */
const rawMcpCopilot = {
  intent: 'SHOW_BRIEF',
  answer:
    "No - Static Jump is excluded for Jordan by the deterministic safety engine. " +
    "Patellofemoral Pain Syndrome contraindicates the 'cardio - plyometric' pattern. " +
    'Low-load exercise stresses knee, which is inside the region affected by Left Knee ' +
    '(recovering). Ask for alternatives and I will only offer options that pass the same checks.',
  citations: [
    {
      source: 'MCP tool: evaluate_exercise_safety',
      detail: 'Static Jump: excluded (deterministic)',
    },
    {
      source: 'MCP tool: get_exercise_provenance',
      detail: 'Static Jump: excluded (deterministic)',
    },
  ],
  chart: null,
  evidence: {},
  generator: 'stub',
  latency_ms: 12.3,
  grounding: {
    mode: 'mcp',
    tools_used: ['evaluate_exercise_safety', 'get_exercise_provenance'],
    authoritative_safety: true,
    safety_corrected: false,
  },
  safety_evidence: {
    exercise_name: 'Static Jump',
    decision: 'excluded',
    reasons: [
      {
        rule_id: 'injury_contraindicated_pattern',
        message:
          "Patellofemoral Pain Syndrome contraindicates the 'cardio - plyometric' pattern.",
      },
      {
        rule_id: 'injury_region_stress',
        message:
          'Low-load exercise stresses knee, which is inside the region affected by Left Knee (recovering).',
      },
    ],
    rule_ids: ['injury_contraindicated_pattern', 'injury_region_stress'],
    graph_paths: [
      'Patellofemoral Pain Syndrome -[CONTRAINDICATES]-> cardio - plyometric -[HAS_PATTERN]-> Static Jump',
      'Jordan Rivera -[HAS_INJURY]-> Left Knee (recovering) -[MAPS_TO]-> Patellofemoral Pain Syndrome -[AFFECTS]-> Patellofemoral Joint',
      'Static Jump -[STRESSES]-> Knee',
      'Patellofemoral Joint -[PART_OF]-> Knee',
    ],
    evidence_note: null,
  },
} as const;

export const memberFixture = raw.member as unknown as MemberSummary;
export const historyFixture = raw.history as unknown as MemberHistory;
export const workoutFixture = raw.workout as unknown as GenerateWorkoutResponse;
export const copilotFixture = raw.copilot as unknown as CopilotResponse;
export const mcpCopilotFixture = rawMcpCopilot as unknown as CopilotResponse;
