export const stages = [
  'interested',
  'applied',
  'oa',
  'interview',
  'offer',
  'rejected',
  'withdrawn',
] as const;

export type Stage = (typeof stages)[number];

export const stageLabel: Record<Stage, string> = {
  interested: 'Interested',
  applied: 'Applied',
  oa: 'Online assessment',
  interview: 'Interview',
  offer: 'Offer',
  rejected: 'Not selected',
  withdrawn: 'Withdrawn',
};

export const stageOptions = stages.map((value) => ({ value, label: stageLabel[value] }));
