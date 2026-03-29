import { type Transition, type Variants } from 'framer-motion';

export const transitions = {
  fast: { duration: 0.15, ease: 'easeOut' } as Transition,
  normal: { duration: 0.25, ease: 'easeOut' } as Transition,
  slow: { duration: 0.35, ease: 'easeOut' } as Transition,
};

export const sidebarVariants: Variants = {
  hidden: {
    width: 0,
    opacity: 0,
    transition: transitions.normal,
  },
  visible: {
    width: 'auto',
    opacity: 1,
    transition: transitions.normal,
  },
};

export const messageVariants: Variants = {
  hidden: {
    opacity: 0,
    y: 10,
  },
  visible: {
    opacity: 1,
    y: 0,
    transition: transitions.normal,
  },
  exit: {
    opacity: 0,
    y: -10,
    transition: transitions.fast,
  },
};

export const canvasPanelVariants: Variants = {
  hidden: {
    width: 0,
    opacity: 0,
    transition: transitions.normal,
  },
  split: {
    width: '45%',
    opacity: 1,
    transition: transitions.normal,
  },
  focused: {
    width: '60%',
    opacity: 1,
    transition: transitions.normal,
  },
};

export const chatPanelVariants: Variants = {
  full: {
    width: '100%',
    flex: 1,
    transition: transitions.normal,
  },
  split: {
    width: '55%',
    flex: '0 0 55%',
    transition: transitions.normal,
  },
  compact: {
    width: '40%',
    flex: '0 0 40%',
    transition: transitions.normal,
  },
};

export const collapseVariants: Variants = {
  collapsed: {
    height: 0,
    opacity: 0,
    transition: transitions.normal,
  },
  expanded: {
    height: 'auto',
    opacity: 1,
    transition: transitions.normal,
  },
};

export const cardHoverVariants: Variants = {
  initial: {
    y: 0,
    boxShadow: '0 1px 2px rgba(0, 0, 0, 0.05)',
  },
  hover: {
    y: -2,
    boxShadow: '0 10px 15px rgba(0, 0, 0, 0.1)',
    transition: transitions.fast,
  },
};

export const selectionCardVariants: Variants = {
  unselected: {
    borderColor: '#2A2A2A',
    backgroundColor: '#141414',
  },
  selected: {
    borderColor: '#6366F1',
    backgroundColor: 'rgba(99, 102, 241, 0.08)',
    transition: transitions.fast,
  },
};

export const modalVariants: Variants = {
  hidden: {
    opacity: 0,
    scale: 0.95,
  },
  visible: {
    opacity: 1,
    scale: 1,
    transition: transitions.normal,
  },
  exit: {
    opacity: 0,
    scale: 0.95,
    transition: transitions.fast,
  },
};

export const overlayVariants: Variants = {
  hidden: { opacity: 0 },
  visible: { opacity: 1, transition: transitions.fast },
  exit: { opacity: 0, transition: transitions.fast },
};

export const mobileCanvasVariants: Variants = {
  hidden: {
    y: '100%',
    transition: transitions.normal,
  },
  visible: {
    y: 0,
    transition: transitions.normal,
  },
};

export const progressVariants: Variants = {
  initial: { width: 0 },
  animate: (progress: number) => ({
    width: `${progress * 100}%`,
    transition: { duration: 0.3, ease: 'easeOut' },
  }),
};

export const typingVariants: Variants = {
  hidden: { opacity: 0 },
  visible: { opacity: 1 },
};

export const canvasSlideInVariants: Variants = {
  hidden: {
    x: '100%',
    opacity: 0,
  },
  visible: {
    x: 0,
    opacity: 1,
    transition: {
      type: 'spring',
      stiffness: 300,
      damping: 30,
    },
  },
  exit: {
    x: '100%',
    opacity: 0,
    transition: transitions.normal,
  },
};

export const stepMessageVariants: Variants = {
  hidden: {
    opacity: 0,
    x: -20,
    scale: 0.95,
  },
  visible: {
    opacity: 1,
    x: 0,
    scale: 1,
    transition: {
      type: 'spring',
      stiffness: 400,
      damping: 25,
    },
  },
  exit: {
    opacity: 0,
    x: 20,
    scale: 0.95,
    transition: transitions.fast,
  },
};
