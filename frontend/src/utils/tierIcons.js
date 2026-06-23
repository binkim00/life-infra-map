import iron from '@/assets/tiers/iron.png'
import bronze from '@/assets/tiers/bronze.png'
import silver from '@/assets/tiers/silver.png'
import gold from '@/assets/tiers/gold.png'
import platinum from '@/assets/tiers/platinum.png'
import diamond from '@/assets/tiers/diamond.png'
import master from '@/assets/tiers/master.png'
import challenger from '@/assets/tiers/challenger.png'

export const tierIconMap = {
  iron,
  bronze,
  silver,
  gold,
  platinum,
  diamond,
  master,
  challenger,
}

export const tierLabelMap = {
  iron: '아이언',
  bronze: '브론즈',
  silver: '실버',
  gold: '골드',
  platinum: '플래티넘',
  diamond: '다이아',
  master: '마스터',
  challenger: '챌린저',
}

export const getTierIcon = (tier) => tierIconMap[tier] || tierIconMap.iron
export const getTierLabel = (tier) => tierLabelMap[tier] || '아이언'
