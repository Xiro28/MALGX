# vLGX - Visual Logic Guided eXtraction

This is an extension of the Logic Guided eXtraction (LGX) framework, which is designed to extract structured information from visual data, such as images or videos. The vLGX framework incorporates the possibility to evaluate visual data to enhance the extraction process, allowing it to understand and interpret the content more effectively.

# Improvment over the original LGX framework, vLGX includes the following features:
- **Visual Evaluation**: vLGX can analyze visual data to extract relevant information, such as identifying objects, actions, or scenes in images or videos. This allows for a more comprehensive understanding of the content being processed.
- Mustache **Templates**: vLGX utilizes mustache templates to insert the values of the atoms into the prompt, allowing for a more dynamic and flexible extraction process. This enables the framework to adapt to different types of visual data and extract information in a more context-aware manner.
- **Decorators**: vLGX includes decorators that can be used to define which information to extract and how to extract it by simply creating a class with the values to extract. More details on how to use the decorators can be found in the documentation.
- **Linked atoms**: vLGX allows for the linking of atoms, which can be used to connect related pieces of information and create a more cohesive representation of the extracted data. Useful when the information is contained in different atoms, but they are related to each other. 
Example:
```prolog
step(5).
main_action(#step, action).
step_description(#step, description).
```
In this example, the `main_action` atom contains the main action being performed at a specific step, while the `step_description` atom contains a description of that step. By linking these two atoms using the `#step` variable, we restrict the extraction on only the description of the main action being performed at that specific step, rather than extracting all the descriptions of all the steps. This allows for a more focused and relevant extraction of information.



# Supported functions of the decorators:
- Over the functions:
    - 'after_kb_run': This function is called after the extraction process is completed. It can be used to perform any necessary post-processing on the extracted data, such as cleaning, formatting, or further analysis.
    - 'after_atoms_extracted(atom_head)': This function is called after a specific atom has been extracted.
- Over a class:
    - 'cardinality': This function can be used to specify the expected number of instances for a particular atom. For example, if you expect only one instance of an atom to be extracted, you can set the cardinality to 1. This can help to ensure that the extraction process is more accurate and relevant, as it will focus on extracting the expected number of instances for each atom.

    - 'knowledge_base': This function can be used to specify the knowledge base that should be used for a particular atom.