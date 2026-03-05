import os
from typing import TypedDict


class AvatarConfig(TypedDict):
    avatar_id: str
    voice_id: str
    look_id: str
    gender: str
    ethnicity: str
    tone: str
    best_for: str
    description: str


# All IDs are read from Railway environment variables.
# Variable naming: HEYGEN_AVATAR_{N}_ID, HEYGEN_AVATAR_{N}_LOOK_ID, HEYGEN_VOICE_{N}_ID
AVATARS: dict[str, AvatarConfig] = {
    'professional_white_female': {
        'avatar_id': os.environ.get('HEYGEN_AVATAR_1_ID', ''),
        'voice_id': os.environ.get('HEYGEN_VOICE_1_ID', ''),
        'look_id': os.environ.get('HEYGEN_AVATAR_1_LOOK_ID', ''),
        'gender': 'female',
        'ethnicity': 'white',
        'tone': 'authoritative, empathetic',
        'best_for': 'General California ads, suburban demographics, wage theft cases',
        'description': (
            'Professional white female attorney. Warm but authoritative. '
            'Suits suburban California audiences and cases involving office/corporate '
            'wrongful termination.'
        ),
    },
    'professional_black_male': {
        'avatar_id': os.environ.get('HEYGEN_AVATAR_2_ID', ''),
        'voice_id': os.environ.get('HEYGEN_VOICE_2_ID', ''),
        'look_id': os.environ.get('HEYGEN_AVATAR_2_LOOK_ID', ''),
        'gender': 'male',
        'ethnicity': 'black',
        'tone': 'confident, direct',
        'best_for': 'Urban California markets, discrimination cases, strong hook delivery',
        'description': (
            'Confident Black male legal advocate. Direct and trustworthy. '
            'Best for discrimination-adjacent cases or urban California demographics '
            '(LA, Bay Area).'
        ),
    },
    'professional_hispanic_female': {
        'avatar_id': os.environ.get('HEYGEN_AVATAR_3_ID', ''),
        'voice_id': os.environ.get('HEYGEN_VOICE_3_ID', ''),
        'look_id': os.environ.get('HEYGEN_AVATAR_3_LOOK_ID', ''),
        'gender': 'female',
        'ethnicity': 'hispanic',
        'tone': 'compassionate, urgent',
        'best_for': 'Southern California, Texas markets, Spanish-speaking adjacent audiences',
        'description': (
            'Compassionate Hispanic female advocate. Strong emotional resonance. '
            'Best for Southern California, Texas, and retaliation or hostile work '
            'environment cases.'
        ),
    },
    'professional_white_male': {
        'avatar_id': os.environ.get('HEYGEN_AVATAR_4_ID', ''),
        'voice_id': os.environ.get('HEYGEN_VOICE_4_ID', ''),
        'look_id': os.environ.get('HEYGEN_AVATAR_4_LOOK_ID', ''),
        'gender': 'male',
        'ethnicity': 'white',
        'tone': 'serious, trustworthy',
        'best_for': 'Conservative markets, older demographics, high-value settlement cases',
        'description': (
            'Serious white male legal professional. Commands immediate trust. '
            'Best for conservative markets, older demographics (45+), and ads '
            'emphasising large settlement figures.'
        ),
    },
    'professional_asian_female': {
        'avatar_id': os.environ.get('HEYGEN_AVATAR_5_ID', ''),
        'voice_id': os.environ.get('HEYGEN_VOICE_5_ID', ''),
        'look_id': os.environ.get('HEYGEN_AVATAR_5_LOOK_ID', ''),
        'gender': 'female',
        'ethnicity': 'asian',
        'tone': 'precise, credible',
        'best_for': 'Bay Area, tech industry wrongful termination, high-income demographics',
        'description': (
            'Precise and credible Asian female legal expert. Highly educated tone. '
            'Best for Bay Area, tech industry wrongful termination cases, and '
            'high-income professional demographics.'
        ),
    },
}


def get_avatar_list_for_claude() -> str:
    lines = []
    for key, av in AVATARS.items():
        lines.append(f'- KEY: {key}')
        lines.append(f'  Description: {av["description"]}')
        lines.append(f'  Best for: {av["best_for"]}')
    return '\n'.join(lines)
